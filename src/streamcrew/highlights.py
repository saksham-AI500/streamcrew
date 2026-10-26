"""Detect unusually busy chat windows and request guarded stream markers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .actions import execute_action, record_marker_result


@dataclass(frozen=True, slots=True)
class WindowStats:
    """Exponentially weighted mean and standard deviation of window counts."""

    mean: float = 0.0
    spread: float = 0.0
    samples: int = 0


def update_window_stats(stats: WindowStats, count: int, alpha: float = 0.2) -> WindowStats:
    """Add one completed window count to exponentially weighted statistics."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be greater than 0 and at most 1")
    delta = count - stats.mean
    mean = stats.mean + alpha * delta
    variance = (1 - alpha) * (stats.spread**2 + alpha * delta**2)
    return WindowStats(mean, variance**0.5, stats.samples + 1)


def is_chat_spike(count: int, mean: float, spread: float) -> bool:
    """Apply the minimum activity floor and three-spread threshold."""
    return count >= 8 and (count - mean) / max(spread, 1.0) >= 3


class HighlightDetector:
    """Count chat in rolling windows and send a marker through the action guard."""

    def __init__(
        self,
        settings: Any,
        mode: str = "auto",
        action_executor: Callable[..., dict[str, Any]] = execute_action,
        clock: Callable[[], datetime] | None = None,
        window_seconds: int = 10,
        minimum_gap_seconds: int = 60,
        alpha: float = 0.2,
        store: Any | None = None,
    ) -> None:
        self.settings = settings
        self.mode = mode
        self.action_executor = action_executor
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.window_seconds = window_seconds
        self.minimum_gap_seconds = minimum_gap_seconds
        self.alpha = alpha
        self.store = store
        self._messages: deque[datetime] = deque()
        self._stats = WindowStats()
        self._bucket: int | None = None
        self._bucket_count = 0
        self._last_marker_at: datetime | None = None

    @property
    def stats(self) -> WindowStats:
        """Return a snapshot of the completed-window baseline."""
        return self._stats

    def _advance_bucket(self, timestamp: datetime) -> None:
        bucket = int(timestamp.timestamp() // self.window_seconds)
        if self._bucket is None:
            self._bucket = bucket
            return
        if bucket <= self._bucket:
            return
        self._stats = update_window_stats(self._stats, self._bucket_count, self.alpha)
        for _ in range(max(0, bucket - self._bucket - 1)):
            self._stats = update_window_stats(self._stats, 0, self.alpha)
        self._bucket = bucket
        self._bucket_count = 0

    def observe_message(self, timestamp: datetime | None = None) -> dict[str, Any] | None:
        """Record one message and return marker status only when a spike fires."""
        now = timestamp or self.clock()
        self._advance_bucket(now)
        cutoff = now.timestamp() - self.window_seconds
        while self._messages and self._messages[0].timestamp() < cutoff:
            self._messages.popleft()
        self._messages.append(now)
        self._bucket_count += 1

        count = len(self._messages)
        if not is_chat_spike(count, self._stats.mean, self._stats.spread):
            return None
        if (
            self._last_marker_at is not None
            and (now - self._last_marker_at).total_seconds() < self.minimum_gap_seconds
        ):
            return None

        self._last_marker_at = now
        action = {"action": "create_marker", "description": "Chat activity spike"}
        result = self.action_executor(action, self.mode, self.settings)
        if self.store is not None:
            record_marker_result(self.store, action, result, source="highlight-detector")
        return {"timestamp": now.isoformat(), "count": count, "result": result}
