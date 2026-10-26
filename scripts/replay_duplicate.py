#!/usr/bin/env python3
"""Replay one captured local EventSub notification through the client handler."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from streamcrew.config import load_config  # noqa: E402
from streamcrew.eventsub import EventSubClient  # noqa: E402
from streamcrew.storage import SQLiteEventStore  # noqa: E402


async def _capture_one_notification(settings) -> str:
    """Connect only to a local mock, trigger once, and return its raw frame."""
    parsed_url = urlparse(settings.eventsub_ws_url)
    if parsed_url.scheme != "ws" or parsed_url.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("EVENTSUB_WS_URL must point to a local ws:// mock server.")

    async with websockets.connect(settings.eventsub_ws_url) as websocket:
        welcome_raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        welcome = json.loads(welcome_raw)
        if welcome.get("metadata", {}).get("message_type") != "session_welcome":
            raise RuntimeError("Local mock did not send session_welcome first.")
        session_id = welcome.get("payload", {}).get("session", {}).get("id")
        if not session_id:
            raise RuntimeError("Local mock welcome did not include a session ID.")

        trigger = subprocess.run(
            [
                "twitch",
                "event",
                "trigger",
                "stream.online",
                "--transport",
                "websocket",
                "--session",
                str(session_id),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if trigger.returncode != 0:
            raise RuntimeError("Twitch CLI could not trigger the local mock event.")

        raw_frame = await asyncio.wait_for(websocket.recv(), timeout=10)
        frame = json.loads(raw_frame)
        if frame.get("metadata", {}).get("message_type") != "notification":
            raise RuntimeError("Local mock did not deliver a notification frame.")
        if not frame.get("metadata", {}).get("message_id"):
            raise RuntimeError("Mock notification has no message ID to deduplicate.")
        return raw_frame


def main() -> int:
    """Replay a notification twice and require exactly one stored event row."""
    settings = load_config(PROJECT_ROOT / ".env")
    raw_frame = asyncio.run(_capture_one_notification(settings))
    database_path = PROJECT_ROOT / "data" / "events.sqlite3"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    frame = json.loads(raw_frame)
    message_id = frame["metadata"]["message_id"]

    with SQLiteEventStore(database_path) as store:
        client = EventSubClient(settings, store)
        client.handle_message(raw_frame)
        client.handle_message(raw_frame)
        count = store._connection.execute(
            "SELECT COUNT(*) FROM events WHERE message_id=?", (message_id,)
        ).fetchone()[0]

    print(f"same raw frame replayed twice: {count} stored row(s)")
    return 0 if count == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
