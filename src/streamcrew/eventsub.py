"""Connect to Twitch EventSub WebSockets and persist fresh notifications."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)
SubscribeCallback = Callable[[str], Awaitable[None] | None]


class EventSubClient:
    """Receive EventSub messages, deduplicate them, and reconnect safely."""

    def __init__(
        self,
        settings: Any,
        store: Any,
        subscribe_callback: SubscribeCallback | None = None,
        websocket_connector: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.websocket_url = settings.eventsub_ws_url
        self.subscribe_callback = subscribe_callback
        self.websocket_connector = websocket_connector or websockets.connect
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._stop = asyncio.Event()
        self._active_websocket: Any | None = None

    async def connect(self, url: str | None = None) -> Any:
        """Open a WebSocket using library defaults, including automatic Pong."""
        return await self.websocket_connector(url or self.websocket_url)

    def handle_welcome(self, message: dict[str, Any]) -> tuple[str, int]:
        """Extract the session ID and keepalive timeout from a welcome frame."""
        if message.get("metadata", {}).get("message_type") != "session_welcome":
            raise ValueError("Expected an EventSub session_welcome message.")
        session = message.get("payload", {}).get("session", {})
        session_id = session.get("id")
        if not session_id:
            raise ValueError("EventSub welcome message has no session ID.")
        timeout = session.get("keepalive_timeout_seconds") or 10
        return str(session_id), int(timeout)

    async def _receive_welcome(self, websocket: Any) -> tuple[str, int]:
        raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        session_id, keepalive_timeout = self.handle_welcome(json.loads(raw))
        logger.info("Connected to EventSub session %s", session_id)
        if self.subscribe_callback is not None:
            result = self.subscribe_callback(session_id)
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=10)
        return session_id, keepalive_timeout

    async def handle_keepalive_timeout(self, websocket: Any) -> None:
        """Close a silent socket so the run loop reconnects and resubscribes."""
        await self.handle_close(websocket)
        raise TimeoutError("EventSub keepalive timed out.")

    async def handle_reconnect_message(
        self, old_websocket: Any, message: dict[str, Any]
    ) -> tuple[Any, int]:
        """Welcome on Twitch's replacement socket before closing the old one."""
        reconnect_url = (
            message.get("payload", {}).get("session", {}).get("reconnect_url")
        )
        if not reconnect_url:
            raise ValueError("EventSub reconnect message has no reconnect URL.")
        new_websocket = await self.connect(str(reconnect_url))
        try:
            _, keepalive_timeout = await self._receive_welcome_without_subscribe(
                new_websocket
            )
        except Exception:
            await self.handle_close(new_websocket)
            raise
        await self.handle_close(old_websocket)
        return new_websocket, keepalive_timeout

    async def _receive_welcome_without_subscribe(self, websocket: Any) -> tuple[str, int]:
        raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        result = self.handle_welcome(json.loads(raw))
        logger.info("Connected to replacement EventSub session %s", result[0])
        return result

    async def handle_close(self, websocket: Any) -> None:
        """Close a socket if it is still open."""
        if websocket is not None:
            await websocket.close()

    def _is_stale(self, timestamp: str) -> bool:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except (AttributeError, ValueError):
            return True
        return self.clock() - parsed > timedelta(minutes=10)

    def _handle_notification(self, message: dict[str, Any]) -> bool:
        metadata = message.get("metadata", {})
        payload = message.get("payload", {})
        message_id = metadata.get("message_id")
        timestamp = metadata.get("message_timestamp")
        if not message_id or not timestamp or self._is_stale(str(timestamp)):
            return False
        return self.store.save_event(
            str(message_id),
            str(metadata.get("message_type", "notification")),
            metadata.get("subscription_type"),
            payload,
        )

    def handle_message(self, raw_message: str) -> bool:
        """Parse one text frame and pass notification frames to the store path."""
        message = json.loads(raw_message)
        if message.get("metadata", {}).get("message_type") != "notification":
            return False
        return self._handle_notification(message)

    async def _serve_connection(self) -> None:
        websocket = await self.connect()
        self._active_websocket = websocket
        _, keepalive_timeout = await self._receive_welcome(websocket)
        try:
            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(
                        websocket.recv(), timeout=keepalive_timeout
                    )
                except asyncio.TimeoutError:
                    await self.handle_keepalive_timeout(websocket)
                except ConnectionClosed as error:
                    await self.handle_close(websocket)
                    if error.code == 4004:
                        return
                    raise

                message = json.loads(raw)
                message_type = message.get("metadata", {}).get("message_type")
                if message_type == "session_keepalive":
                    continue
                if message_type == "session_reconnect":
                    websocket, keepalive_timeout = await self.handle_reconnect_message(
                        websocket, message
                    )
                    self._active_websocket = websocket
                    continue
                if message_type == "notification":
                    self.handle_message(raw)
        finally:
            if websocket is self._active_websocket:
                self._active_websocket = None
            await self.handle_close(websocket)

    async def run(self) -> None:
        """Reconnect after failures, using exponential backoff capped at 60s."""
        retry_delay = 1
        while not self._stop.is_set():
            try:
                await self._serve_connection()
                retry_delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "EventSub connection ended (%s); retrying in %s second(s).",
                    type(error).__name__,
                    retry_delay,
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=retry_delay)
                except asyncio.TimeoutError:
                    pass
                retry_delay = min(retry_delay * 2, 60)

    async def close(self) -> None:
        """Stop the run loop and close the current socket."""
        self._stop.set()
        await self.handle_close(self._active_websocket)
