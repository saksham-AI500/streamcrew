"""Replay a saved synthetic chat trace through the dry-run highlight detector."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from streamcrew.highlights import HighlightDetector  # noqa: E402


def main() -> int:
    """Print each timestamp at which the fixture crosses the spike threshold."""
    fixture = json.loads((PROJECT_ROOT / "fixtures" / "chat_trace.json").read_text())
    detector = HighlightDetector(SimpleNamespace(dry_run=True), mode="auto")
    fired = 0
    for raw_timestamp in fixture["messages"]:
        result = detector.observe_message(datetime.fromisoformat(raw_timestamp))
        if result is not None:
            fired += 1
            print(f"fired at {result['timestamp']} (window count={result['count']})")
    if not fired:
        print("no spike detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
