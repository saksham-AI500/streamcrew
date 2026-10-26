"""Tests for EventSub session handling, duplicate filtering, and freshness."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from streamcrew.eventsub import EventSubClient
from streamcrew.storage import SQLiteEventStore


class FakeWebSocket:
    def __init__(self, messages=(), on_recv=None):
        self.messages = list(messages)
        self.on_recv = on_recv
        self.closed = False

    async def recv(self):
        if self.on_recv is not None:
            return self.on_recv()
        return self.messages.pop(0)

    async def close(self):
        self.closed = True


def _welcome(session_id="session-new"):
    return json.dumps(
        {
            "metadata": {"message_type": "session_welcome"},
            "payload": {
                "session": {
                    "id": session_id,
                    "keepalive_timeout_seconds": 10,
                }
            },
        }
    )


def _notification(message_id, timestamp, subscription_type="channel.chat.message"):
    return {
        "metadata": {
            "message_id": message_id,
            "message_type": "notification",
            "message_timestamp": timestamp,
            "subscription_type": subscription_type,
        },
        "payload": {"event": {"message": {"text": "hello"}}},
    }


def test_welcome_extracts_session_and_keepalive_timeout(tmp_path):
    client = EventSubClient(
        SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
        SQLiteEventStore(tmp_path / "events.sqlite3"),
    )

    assert client.handle_welcome(json.loads(_welcome("session-42"))) == ("session-42", 10)
    client.store.close()


def test_duplicate_notifications_are_skipped_and_old_notifications_ignored(tmp_path):
    now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        client = EventSubClient(
            SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
            store,
            clock=lambda: now,
        )
        fresh = _notification("message-1", "2026-10-26T11:59:00Z")
        stale = _notification("message-old", "2026-10-26T11:49:59Z")

        assert client._handle_notification(fresh) is True
        assert client._handle_notification(fresh) is False
        assert client._handle_notification(stale) is False
        rows = store._connection.execute(
            "SELECT message_id, message_type, subscription_type FROM events"
        ).fetchall()

    assert rows == [("message-1", "notification", "channel.chat.message")]


def test_same_raw_notification_frame_stores_one_row(tmp_path):
    raw_frame = json.dumps(
        _notification("message-replayed", "2026-10-26T11:59:00Z")
    )
    now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        client = EventSubClient(
            SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
            store,
            clock=lambda: now,
        )

        assert client.handle_message(raw_frame) is True
        assert client.handle_message(raw_frame) is False
        rows = store._connection.execute(
            "SELECT COUNT(*) FROM events WHERE message_id=?", ("message-replayed",)
        ).fetchone()[0]

    assert rows == 1


def test_reconnect_welcomes_new_socket_before_closing_old(tmp_path):
    old_socket = FakeWebSocket()
    new_socket = FakeWebSocket(on_recv=lambda: _welcome("session-reconnected"))
    connected_urls = []

    async def connector(url):
        connected_urls.append(url)
        return new_socket

    client = EventSubClient(
        SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
        SQLiteEventStore(tmp_path / "events.sqlite3"),
        websocket_connector=connector,
    )
    reconnect_message = {
        "payload": {"session": {"reconnect_url": "ws://new-edge.test/session"}}
    }

    import asyncio

    returned_socket, timeout = asyncio.run(
        client.handle_reconnect_message(old_socket, reconnect_message)
    )

    assert connected_urls == ["ws://new-edge.test/session"]
    assert returned_socket is new_socket
    assert timeout == 10
    assert old_socket.closed is True
