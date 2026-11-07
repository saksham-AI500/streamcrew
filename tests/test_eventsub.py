"""Tests for EventSub session handling, duplicate filtering, and freshness."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import websockets

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


def _keepalive():
    return json.dumps({"metadata": {"message_type": "session_keepalive"}})


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


def test_notification_callback_runs_only_after_first_store(tmp_path):
    now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    handled = []
    raw_frame = json.dumps(
        _notification("message-callback", "2026-10-26T11:59:00Z")
    )
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        client = EventSubClient(
            SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
            store,
            clock=lambda: now,
            notification_callback=handled.append,
        )

        assert client.handle_message(raw_frame) is True
        assert client.handle_message(raw_frame) is False

    assert len(handled) == 1
    assert handled[0]["metadata"]["message_id"] == "message-callback"


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


def test_keepalive_at_ninety_percent_timeout_survives_and_silent_socket_reconnects(
    tmp_path,
):
    async def exercise():
        first = FakeWebSocket([_welcome(), _keepalive()])
        second = FakeWebSocket([_welcome("session-after-timeout")])
        sockets = [first, second]
        fake_now = [0.0]
        seen_waits = []

        async def connector(_url):
            socket = sockets.pop(0)
            if not sockets:
                # End the loop after proving it established a replacement.
                client._stop.set()
            return socket

        async def fake_wait_for(awaitable, timeout):
            if not isinstance(awaitable, asyncio.Future) and not asyncio.iscoroutine(awaitable):
                raise AssertionError("expected an awaitable")
            if asyncio.iscoroutine(awaitable) and awaitable.cr_code.co_name == "recv":
                seen_waits.append(timeout)
                if len(seen_waits) == 1:
                    fake_now[0] += timeout * 0.9
                    return await awaitable
                fake_now[0] += timeout
                awaitable.close()
                raise asyncio.TimeoutError
            # Retry backoff is also advanced virtually, without wall-clock sleep.
            fake_now[0] += timeout
            awaitable.close()
            raise asyncio.TimeoutError

        client = EventSubClient(
            SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
            SQLiteEventStore(tmp_path / "events.sqlite3"),
            websocket_connector=connector,
            wait_for=fake_wait_for,
        )
        await client.run()
        assert seen_waits == [15, 15]
        assert fake_now[0] >= 13.5 + 15 + 1
        assert first.closed is True
        assert second.closed is True
        client.store.close()

    asyncio.run(exercise())


def test_connect_automatically_answers_ping_with_pong(tmp_path):
    async def exercise():
        pong_received = asyncio.Event()

        async def server_handler(websocket):
            waiter = await websocket.ping(b"streamcrew-ping-check")
            await asyncio.wait_for(waiter, timeout=1)
            pong_received.set()

        async with websockets.serve(server_handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            store = SQLiteEventStore(tmp_path / "events.sqlite3")
            client = EventSubClient(
                SimpleNamespace(eventsub_ws_url=f"ws://127.0.0.1:{port}/ws"),
                store,
            )
            websocket = await client.connect()
            await asyncio.wait_for(pong_received.wait(), timeout=2)
            await websocket.close()
            store.close()

    asyncio.run(exercise())


def test_authentication_close_4004_stops_without_reconnecting(tmp_path):
    from websockets.exceptions import ConnectionClosedError
    from websockets.frames import Close

    async def exercise():
        holder = {}
        connections = []

        class AuthFailSocket(FakeWebSocket):
            def __init__(self):
                super().__init__([_welcome("session-auth")])

            async def recv(self):
                if self.messages:
                    return self.messages.pop(0)
                raise ConnectionClosedError(Close(4004, "auth failed"), None)

        async def connector(_url):
            connections.append(1)
            if len(connections) > 1:
                raise AssertionError("reconnected after an auth failure")
            socket = AuthFailSocket()
            holder["socket"] = socket
            return socket

        async def fake_wait_for(awaitable, timeout):
            if asyncio.iscoroutine(awaitable) and awaitable.cr_code.co_name == "recv":
                return await awaitable
            holder["client"]._stop.set()
            awaitable.close()
            return True

        client = EventSubClient(
            SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
            SQLiteEventStore(tmp_path / "events.sqlite3"),
            websocket_connector=connector,
            wait_for=fake_wait_for,
        )
        holder["client"] = client
        await client.run()

        assert len(connections) == 1
        assert client._stop.is_set()
        assert holder["socket"].closed is True
        client.store.close()

    asyncio.run(exercise())
