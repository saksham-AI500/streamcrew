"""Redact chat text and event payloads for safe agent and overlay output."""

from __future__ import annotations

import copy
import re
from typing import Any

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def redact_text(text: str, max_length: int = 40) -> str:
    """Remove URLs and email addresses, collapse whitespace, and truncate."""
    if not isinstance(text, str):
        return ""
    cleaned = _URL_RE.sub("[link]", text)
    cleaned = _EMAIL_RE.sub("[email]", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_length:
        return cleaned[: max(0, max_length - 1)].rstrip() + "…"
    return cleaned


def redact_event(event: dict[str, Any], max_length: int = 40) -> dict[str, Any]:
    """Return a copy of an event record with any chat message text redacted."""
    copied = copy.deepcopy(event)
    payload = copied.get("payload")
    if isinstance(payload, dict):
        inner = payload.get("event") if isinstance(payload.get("event"), dict) else payload
        msg = inner.get("message") if isinstance(inner, dict) else None
        if isinstance(msg, dict) and isinstance(msg.get("text"), str):
            msg["text"] = redact_text(msg["text"], max_length=max_length)
            if isinstance(msg.get("fragments"), list):
                msg.pop("fragments", None)
        elif isinstance(inner, dict) and isinstance(inner.get("text"), str):
            inner["text"] = redact_text(inner["text"], max_length=max_length)
    return copied
