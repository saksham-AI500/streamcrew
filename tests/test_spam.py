"""Unit and fixture tests for the pure spam burst detector (SRS FR-31 to FR-33)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from streamcrew.config import load_config
from streamcrew.spam import SpamDetector, detect_spam_burst, normalize_text

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
START = datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)


def _msg(
    user_id: str,
    text: str,
    offset_seconds: float,
    *,
    login: str | None = None,
) -> dict[str, object]:
    timestamp = (START + timedelta(seconds=offset_seconds)).isoformat()
    user_login = login or f"user_{user_id}"
    return {
        "metadata": {
            "message_id": f"msg-{user_id}-{offset_seconds}",
            "message_type": "notification",
            "subscription_type": "channel.chat.message",
            "message_timestamp": timestamp,
        },
        "payload": {
            "event": {
                "chatter_user_id": user_id,
                "chatter_user_login": user_login,
                "chatter_user_name": user_login,
                "message": {"text": text},
            }
        },
    }


def test_five_accounts_same_text_within_ten_seconds_fires_once() -> None:
    """Section 5 case 1: 5 accounts, same text, within 10 s -> Fires once."""
    messages = [
        _msg(f"u{i}", "buy cheap followers now", i * 1.5) for i in range(1, 6)
    ]
    clock = lambda: START + timedelta(seconds=8)

    incident = detect_spam_burst(messages, clock)

    assert incident is not None
    assert incident["accounts"] == 5
    assert incident["messages"] == 5
    assert incident["remaining_accounts"] == 0
    assert len(incident["targets"]) == 5
    assert [t["user_id"] for t in incident["targets"]] == ["u1", "u2", "u3", "u4", "u5"]


def test_four_accounts_does_not_fire() -> None:
    """Section 5 case 2: 4 accounts -> Does not fire."""
    messages = [
        _msg(f"u{i}", "buy cheap followers now", i * 1.5) for i in range(1, 5)
    ]
    clock = lambda: START + timedelta(seconds=8)

    assert detect_spam_burst(messages, clock) is None


def test_single_account_repeating_thirty_times_does_not_fire() -> None:
    """Section 5 case 3: 1 account repeating 30 times -> Does not fire as a burst."""
    messages = [
        _msg("repeat-user", "spam phrase repeated", i * 0.2) for i in range(30)
    ]
    clock = lambda: START + timedelta(seconds=6)

    assert detect_spam_burst(messages, clock) is None


def test_same_text_spread_over_sixty_seconds_does_not_fire() -> None:
    """Section 5 case 4: Same text, spread over 60 s -> Does not fire."""
    messages = [
        _msg(f"u{i}", "slow repeated text", i * 12.0) for i in range(5)
    ]
    clock = lambda: START + timedelta(seconds=48)

    assert detect_spam_burst(messages, clock) is None


def test_text_differing_by_case_spacing_punctuation_and_urls_counts_as_same() -> None:
    """Section 5 case 5: Case, spacing, URLs, or trailing/repeated punctuation match."""
    variants = [
        "FREE COINS NOW!!!",
        "  free   coins   now! ",
        "free coins now???",
        "Free Coins Now... https://scam.example.test/link",
        "free coins now",
    ]
    messages = [
        _msg(f"u{i}", text, float(i)) for i, text in enumerate(variants, start=1)
    ]
    clock = lambda: START + timedelta(seconds=6)

    incident = detect_spam_burst(messages, clock)

    assert normalize_text("  FREE   COINS NOW!!! https://example.test/x ") == "free coins now"
    assert incident is not None
    assert incident["normalized_text"] == "free coins now"
    assert incident["accounts"] == 5
    assert "https://" not in incident["sample"]


def test_burst_of_forty_accounts_caps_targets_at_twenty_five() -> None:
    """Section 5 case 6: Burst of 40 accounts -> 25 targets plus remaining count."""
    messages = [
        _msg(f"bot-{i:02d}", "mass raid spam text", i * 0.2) for i in range(1, 41)
    ]
    clock = lambda: START + timedelta(seconds=8)

    incident = detect_spam_burst(messages, clock)

    assert incident is not None
    assert len(incident["targets"]) == 25
    assert incident["accounts"] == 40
    assert incident["remaining_accounts"] == 15
    assert incident["summary"]["accounts"] == 40
    assert incident["summary"]["remaining_accounts"] == 15


def test_cooldown_blocks_second_incident_until_cooldown_ends() -> None:
    """Section 5 case 7: Fires, then same burst continues -> blocked until cooldown ends."""
    initial = [_msg(f"u{i}", "raid wave message", float(i)) for i in range(1, 6)]
    first_time = START + timedelta(seconds=5)
    first_incident = detect_spam_burst(initial, lambda: first_time)
    assert first_incident is not None

    continued = initial + [
        _msg(f"u{i}", "raid wave message", float(i)) for i in range(6, 12)
    ]
    during_cooldown = START + timedelta(seconds=11)
    assert (
        detect_spam_burst(
            continued,
            lambda: during_cooldown,
            last_incident_at=first_incident["detected_at"],
        )
        is None
    )
    # Also blocked when full history is passed without explicit last_incident_at
    later_in_cooldown = initial + [
        _msg(f"u{i}", "raid wave message", 20.0 + i) for i in range(6, 12)
    ]
    assert detect_spam_burst(later_in_cooldown, lambda: START + timedelta(seconds=26)) is None

    # After 60s cooldown from the first burst at t=5s, a new burst at t=66..70s fires
    after_cooldown_msgs = initial + [
        _msg(f"u{i}", "raid wave message", 65.0 + i) for i in range(1, 6)
    ]
    after_cooldown = START + timedelta(seconds=70)
    re_fired = detect_spam_burst(
        after_cooldown_msgs,
        lambda: after_cooldown,
        last_incident_at=first_incident["detected_at"],
    )
    assert re_fired is not None
    assert re_fired["accounts"] == 5


def test_spam_detector_stateful_helper_enforces_cooldown_across_stream() -> None:
    """Stateful SpamDetector wrapper fires once on a burst and blocks until cooldown."""
    current = START
    detector = SpamDetector(clock=lambda: current)
    fired = []
    for i in range(1, 10):
        current = START + timedelta(seconds=i)
        incident = detector.observe_message(_msg(f"u{i}", "continuous spam", float(i)))
        if incident is not None:
            fired.append(incident)
    assert len(fired) == 1
    assert fired[0]["accounts"] == 5


def test_empty_or_one_character_messages_are_ignored() -> None:
    """Section 5 case 8: Empty or one-character messages -> Ignored."""
    empty_msgs = [_msg(f"u{i}", "   ", float(i)) for i in range(1, 8)]
    one_char_msgs = [_msg(f"a{i}", "x", float(i)) for i in range(1, 8)]
    punct_only_msgs = [_msg(f"p{i}", "!!!", float(i)) for i in range(1, 8)]
    clock = lambda: START + timedelta(seconds=8)

    assert detect_spam_burst(empty_msgs + one_char_msgs + punct_only_msgs, clock) is None


def test_fixtures_spam_burst_and_quiet() -> None:
    """Burst fixture fires once; quiet fixture never fires."""
    burst_data = json.loads((FIXTURES_DIR / "spam_burst.json").read_text(encoding="utf-8"))
    quiet_data = json.loads((FIXTURES_DIR / "spam_quiet.json").read_text(encoding="utf-8"))
    clock = lambda: datetime(2026, 11, 5, 12, 0, 7, tzinfo=timezone.utc)

    burst_incident = detect_spam_burst(burst_data["messages"], clock)
    quiet_incident = detect_spam_burst(quiet_data["messages"], clock)

    assert burst_incident is not None
    assert burst_incident["accounts"] == 6
    assert len(burst_incident["targets"]) == 6
    assert quiet_incident is None


def test_config_loads_srs_spam_defaults(monkeypatch, tmp_path) -> None:
    """Config exposes SRS default parameters for spam detection and grouping."""
    for key in (
        "TWITCH_CLIENT_ID",
        "TWITCH_USER_ACCESS_TOKEN",
        "TWITCH_BROADCASTER_ID",
        "DRY_RUN",
        "SPAM_MIN_ACCOUNTS",
        "SPAM_WINDOW_SECONDS",
        "SPAM_COOLDOWN_SECONDS",
        "SPAM_TIMEOUT_SECONDS",
        "GROUP_CAP",
        "ACTION_PACING_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TWITCH_CLIENT_ID=cid\n"
        "TWITCH_USER_ACCESS_TOKEN=tok\n"
        "TWITCH_BROADCASTER_ID=bid\n",
        encoding="utf-8",
    )

    cfg = load_config(env_file)

    assert cfg.spam_min_accounts == 5
    assert cfg.spam_window_seconds == 10
    assert cfg.spam_cooldown_seconds == 60
    assert cfg.spam_timeout_seconds == 600
    assert cfg.group_cap == 25
    assert cfg.action_pacing_seconds == 0.5


def test_detector_processes_thousand_messages_under_hundred_ms() -> None:
    """NFR-01 / Section 6: 1,000 messages processed in under 100 ms."""
    messages = [
        _msg(f"viewer-{i}", f"unique message number {i}", (i % 10) * 0.9)
        for i in range(1000)
    ]
    clock = lambda: START + timedelta(seconds=9)

    t0 = time.perf_counter()
    result = detect_spam_burst(messages, clock)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert result is None
    assert elapsed_ms < 100.0
