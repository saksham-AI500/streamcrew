"""Test chat-spike math and marker cooldowns using synthetic timestamps."""

from datetime import datetime, timedelta, timezone

from streamcrew.highlights import (
    HighlightDetector,
    WindowStats,
    is_chat_spike,
    update_window_stats,
)
from streamcrew.storage import SQLiteEventStore


class DrySettings:
    """Settings that guarantee the action guard never sends a Twitch request."""

    dry_run = True


def _warm_detector(executor, *, minimum_gap: int = 60) -> HighlightDetector:
    """Build a baseline from two messages in each of ten quiet windows."""
    detector = HighlightDetector(
        DrySettings(), action_executor=executor, minimum_gap_seconds=minimum_gap
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for bucket in range(10):
        for second in (0, 1):
            detector.observe_message(start + timedelta(seconds=bucket * 10 + second))
    return detector


def test_ewma_and_spike_threshold_are_pure_functions() -> None:
    """The score uses the previous mean/spread and enforces an eight-message floor."""
    updated = update_window_stats(WindowStats(), 5, alpha=0.2)
    assert updated.mean == 1
    assert updated.spread == 2
    assert not is_chat_spike(7, 0, 0)
    assert is_chat_spike(8, 0, 1)
    assert not is_chat_spike(8, 6, 1)


def test_quiet_trace_never_fires() -> None:
    """Steady low message counts remain below the required minimum floor."""
    calls = []
    detector = _warm_detector(lambda *args: calls.append(args) or {"status": "dry_run"})
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for bucket in range(10, 15):
        for second in (0, 1):
            assert detector.observe_message(
                start + timedelta(seconds=bucket * 10 + second)
            ) is None
    assert calls == []


def test_activity_spike_fires_once_and_uses_create_marker_action() -> None:
    """A burst after a quiet baseline requests a marker through the injected action path."""
    calls = []
    detector = _warm_detector(lambda *args: calls.append(args) or {"status": "dry_run"})
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    results = [
        detector.observe_message(start + timedelta(seconds=101, milliseconds=ms))
        for ms in range(8)
    ]
    fired = [result for result in results if result is not None]
    assert len(fired) == 1
    assert fired[0]["count"] == 8
    assert calls[0][0] == {
        "action": "create_marker",
        "description": "Chat activity spike",
    }
    assert calls[0][1:] == ("auto", detector.settings)


def test_marker_gap_blocks_a_second_spike_inside_sixty_seconds() -> None:
    """A later burst inside the configured gap does not make another marker call."""
    calls = []
    detector = _warm_detector(lambda *args: calls.append(args) or {"status": "dry_run"})
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = [detector.observe_message(start + timedelta(seconds=101 + i)) for i in range(8)]
    second = [detector.observe_message(start + timedelta(seconds=111 + i)) for i in range(8)]
    assert sum(result is not None for result in first) == 1
    assert all(result is None for result in second)
    assert len(calls) == 1


def test_successful_highlight_marker_is_saved_for_the_overlay(tmp_path):
    """A successful detector marker becomes a marker.created event-log row."""
    result = {
        "status": "sent",
        "status_code": 200,
        "data": {"data": [{"id": "highlight-marker", "description": "Chat spike"}]},
    }
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        detector = _warm_detector(lambda *_: result)
        detector.store = store
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fired = [
            detector.observe_message(start + timedelta(seconds=101 + i))
            for i in range(8)
        ]
        markers = [
            event
            for event in store.list_events()
            if event["subscription_type"] == "marker.created"
        ]

    assert sum(item is not None for item in fired) == 1
    assert len(markers) == 1
    assert markers[0]["message_id"] == "marker:highlight-marker"
