"""Pure spam-burst detector over recent chat messages (SRS FR-31 to FR-33)."""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Sequence

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_REPEATED_PUNCT_RE = re.compile(r"([^\w\s])\1+")
_EDGE_PUNCT_RE = re.compile(r"^[^\w\s]+|[^\w\s]+$")


def normalize_text(text: str) -> str:
    """Lowercase, strip URLs and edge/repeated punctuation, and collapse spaces."""
    if not isinstance(text, str):
        return ""
    cleaned = _URL_RE.sub(" ", text.lower())
    cleaned = _REPEATED_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = " ".join(cleaned.split())
    cleaned = _EDGE_PUNCT_RE.sub("", cleaned)
    return " ".join(cleaned.split())


def redact_sample(text: str, max_length: int = 40) -> str:
    """Strip URLs and emails from a sample and truncate to at most max_length."""
    if not isinstance(text, str):
        return ""
    cleaned = _URL_RE.sub("", text)
    cleaned = _EMAIL_RE.sub("[redacted]", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_length]


def _parse_timestamp(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return (
                parsed
                if parsed.tzinfo is not None
                else parsed.replace(tzinfo=timezone.utc)
            )
        except ValueError:
            return fallback
    return fallback


def _extract_message(item: Any, fallback_time: datetime) -> tuple[str, str, str, datetime] | None:
    """Extract (user_id, login, raw_text, timestamp) from an EventSub or test dict."""
    if not isinstance(item, dict):
        return None
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    sub_type = metadata.get("subscription_type") or item.get("subscription_type")
    if sub_type is not None and sub_type != "channel.chat.message":
        return None

    payload = item.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("event"), dict):
        event = payload["event"]
    elif isinstance(payload, dict):
        event = payload
    else:
        event = item

    user_id = str(
        event.get("chatter_user_id")
        or event.get("user_id")
        or ""
    ).strip()
    if not user_id:
        return None
    login = str(
        event.get("chatter_user_login")
        or event.get("login")
        or event.get("chatter_user_name")
        or user_id
    ).strip()

    msg_obj = event.get("message")
    if isinstance(msg_obj, dict):
        raw_text = msg_obj.get("text", "")
    elif isinstance(msg_obj, str):
        raw_text = msg_obj
    else:
        raw_text = event.get("text", "")
    if not isinstance(raw_text, str):
        return None

    raw_ts = (
        metadata.get("message_timestamp")
        or item.get("received_at")
        or item.get("timestamp")
        or event.get("timestamp")
    )
    timestamp = _parse_timestamp(raw_ts, fallback_time)
    return user_id, login, raw_text, timestamp


def _had_prior_burst(
    entries: list[tuple[str, str, str, datetime]],
    window_seconds: int,
    min_accounts: int,
) -> bool:
    """Return True if entries already formed a burst in any window_seconds span."""
    if len(entries) < min_accounts:
        return False
    for idx, (_, _, _, end_ts) in enumerate(entries):
        start_cutoff = end_ts - timedelta(seconds=window_seconds)
        accounts = {
            uid
            for uid, _, _, ts in entries[: idx + 1]
            if start_cutoff <= ts <= end_ts
        }
        if len(accounts) >= min_accounts:
            return True
    return False


def detect_spam_burst(
    messages: Sequence[dict[str, Any]] | dict[str, Any],
    clock: Callable[[], datetime] | datetime | None = None,
    settings: Any | None = None,
    *,
    last_incident_at: datetime | str | None = None,
    min_accounts: int | None = None,
    window_seconds: int | None = None,
    cooldown_seconds: int | None = None,
    group_cap: int | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any] | None:
    """Pure function: inspect recent messages at clock time and return an incident or None."""
    if isinstance(messages, dict):
        raw_list = messages.get("messages", [])
    else:
        raw_list = messages
    if not raw_list:
        return None

    resolved_min_accounts = (
        min_accounts
        if min_accounts is not None
        else int(getattr(settings, "spam_min_accounts", 5))
    )
    resolved_window = (
        window_seconds
        if window_seconds is not None
        else int(getattr(settings, "spam_window_seconds", 10))
    )
    resolved_cooldown = (
        cooldown_seconds
        if cooldown_seconds is not None
        else int(getattr(settings, "spam_cooldown_seconds", 60))
    )
    resolved_cap = (
        group_cap
        if group_cap is not None
        else int(getattr(settings, "group_cap", 25))
    )
    resolved_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else int(getattr(settings, "spam_timeout_seconds", 600))
    )

    if callable(clock):
        now = clock()
    elif isinstance(clock, datetime):
        now = clock
    else:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if last_incident_at is not None:
        prior_dt = _parse_timestamp(last_incident_at, now)
        if (now - prior_dt).total_seconds() < resolved_cooldown:
            return None

    window_cutoff = now - timedelta(seconds=resolved_window)
    cooldown_cutoff = now - timedelta(seconds=max(resolved_cooldown, resolved_window))

    by_text_window: dict[str, list[tuple[str, str, str, datetime]]] = {}
    by_text_prior: dict[str, list[tuple[str, str, str, datetime]]] = {}

    for item in raw_list:
        extracted = _extract_message(item, now)
        if extracted is None:
            continue
        user_id, login, raw_text, ts = extracted
        if ts > now or ts < cooldown_cutoff:
            continue
        norm = normalize_text(raw_text)
        if len(norm) <= 1:
            continue
        if ts >= window_cutoff:
            by_text_window.setdefault(norm, []).append((user_id, login, raw_text, ts))
        else:
            by_text_prior.setdefault(norm, []).append((user_id, login, raw_text, ts))

    for norm, window_entries in by_text_window.items():
        if len(window_entries) < resolved_min_accounts:
            continue
        distinct_targets: dict[str, dict[str, str]] = {}
        for user_id, login, _, _ in window_entries:
            if user_id not in distinct_targets:
                distinct_targets[user_id] = {"user_id": user_id, "login": login}

        total_accounts = len(distinct_targets)
        if total_accounts < resolved_min_accounts:
            continue

        if last_incident_at is None and _had_prior_burst(
            by_text_prior.get(norm, []), resolved_window, resolved_min_accounts
        ):
            continue

        all_targets = list(distinct_targets.values())
        capped_targets = all_targets[:resolved_cap]
        remaining_accounts = max(0, total_accounts - len(capped_targets))
        timestamps = [ts for _, _, _, ts in window_entries]
        sample = redact_sample(window_entries[0][2]) or norm[:40]
        total_messages = len(window_entries)

        return {
            "kind": "spam_burst",
            "normalized_text": norm,
            "sample": sample,
            "accounts": total_accounts,
            "messages": total_messages,
            "remaining_accounts": remaining_accounts,
            "window_seconds": resolved_window,
            "duration_seconds": resolved_timeout,
            "detected_at": now.isoformat(),
            "window_start": min(timestamps).isoformat(),
            "window_end": max(timestamps).isoformat(),
            "targets": capped_targets,
            "summary": {
                "accounts": total_accounts,
                "messages": total_messages,
                "remaining_accounts": remaining_accounts,
                "window_seconds": resolved_window,
                "sample": sample,
            },
        }
    return None


class SpamDetector:
    """Rolling-window wrapper around detect_spam_burst for live or simulated streams."""

    def __init__(
        self,
        settings: Any | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._buffer: deque[dict[str, Any]] = deque()
        self._last_incident_at: datetime | None = None
        self._last_incident_text: str | None = None

    def observe_message(
        self,
        message: dict[str, Any],
        timestamp: datetime | None = None,
        *,
        include_updates: bool = False,
    ) -> dict[str, Any] | None:
        """Append one message and return an incident when a burst fires."""
        now = timestamp or self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cooldown = int(getattr(self.settings, "spam_cooldown_seconds", 60))
        window = int(getattr(self.settings, "spam_window_seconds", 10))
        horizon = now - timedelta(seconds=max(cooldown, window) + 1)

        self._buffer.append(message)
        while self._buffer:
            extracted = _extract_message(self._buffer[0], now)
            if extracted is not None and extracted[3] < horizon:
                self._buffer.popleft()
            else:
                break

        if (
            self._last_incident_at is not None
            and (now - self._last_incident_at).total_seconds() < cooldown
        ):
            if not include_updates:
                return None
            updated = detect_spam_burst(
                list(self._buffer),
                clock=lambda: now,
                settings=self.settings,
                last_incident_at=None,
            )
            if (
                updated is not None
                and updated.get("normalized_text") == self._last_incident_text
            ):
                updated["is_update"] = True
                return updated
            return None

        incident = detect_spam_burst(
            list(self._buffer),
            clock=lambda: now,
            settings=self.settings,
            last_incident_at=self._last_incident_at,
        )
        if incident is not None:
            self._last_incident_at = now
            self._last_incident_text = incident.get("normalized_text")
        return incident


def build_spam_approval_action(
    incident: dict[str, Any],
    *,
    reason: str = "spam burst",
    group_cap: int = 25,
) -> dict[str, Any]:
    """Build the grouped ban_user action_json payload from a spam incident."""
    duration = int(incident.get("duration_seconds", 600))
    targets = list(incident.get("targets", []))[:group_cap]
    summary = dict(incident.get("summary") or {})
    summary.setdefault("accounts", int(incident.get("accounts", len(targets))))
    summary.setdefault("messages", int(incident.get("messages", len(targets))))
    summary.setdefault(
        "remaining_accounts",
        max(0, summary["accounts"] - len(targets)),
    )
    summary.setdefault("window_seconds", int(incident.get("window_seconds", 10)))
    summary["sample"] = redact_sample(str(summary.get("sample") or incident.get("sample") or ""))
    return {
        "action": "ban_user",
        "duration": duration,
        "duration_seconds": duration,
        "reason": reason,
        "targets": targets,
        "results": [],
        "summary": summary,
    }
