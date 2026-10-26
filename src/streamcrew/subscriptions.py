"""Create and track the small set of EventSub WebSocket subscriptions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Subscription:
    """The local view of one Twitch EventSub subscription."""

    id: str
    type: str
    status: str
    cost: int


SUBSCRIPTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("stream.online", "1", "broadcaster"),
    ("stream.offline", "1", "broadcaster"),
    ("channel.chat.message", "1", "chat"),
    ("channel.raid", "1", "raid"),
    ("channel.follow", "2", "follow"),
    ("channel.chat.notification", "1", "chat"),
)
MAX_TOTAL_COST = 10
SUBSCRIPTION_COST = 1


class SubscriptionManager:
    """Ensure required WebSocket subscriptions exist without duplicating them."""

    def __init__(self, settings: Any, http_client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.url = settings.eventsub_subscriptions_url
        self._http_client = http_client
        self.subscriptions: list[Subscription] = []

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.twitch_user_access_token}",
            "Client-Id": self.settings.twitch_client_id,
            "Content-Type": "application/json",
        }

    def _condition(self, kind: str) -> dict[str, str]:
        broadcaster_id = self.settings.twitch_broadcaster_id
        if kind == "broadcaster":
            return {"broadcaster_user_id": broadcaster_id}
        if kind == "chat":
            return {"broadcaster_user_id": broadcaster_id, "user_id": broadcaster_id}
        if kind == "raid":
            return {"to_broadcaster_user_id": broadcaster_id}
        if kind == "follow":
            return {
                "broadcaster_user_id": broadcaster_id,
                "moderator_user_id": broadcaster_id,
            }
        raise ValueError(f"Unknown subscription condition kind: {kind}")

    def _specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": event_type,
                "version": version,
                "condition": self._condition(condition_kind),
                "transport": {
                    "method": "websocket",
                    "session_id": self._session_id,
                },
            }
            for event_type, version, condition_kind in SUBSCRIPTION_SPECS
        ]

    @staticmethod
    def _as_subscription(item: dict[str, Any]) -> Subscription:
        return Subscription(
            id=str(item.get("id", "")),
            type=str(item.get("type", "")),
            status=str(item.get("status", "unknown")),
            cost=int(item.get("cost", SUBSCRIPTION_COST)),
        )

    def _matches(self, existing: dict[str, Any], spec: dict[str, Any]) -> bool:
        return (
            existing.get("type") == spec["type"]
            and str(existing.get("version")) == spec["version"]
            and existing.get("condition") == spec["condition"]
            and existing.get("transport", {}).get("method") == "websocket"
            and existing.get("transport", {}).get("session_id")
            == self._session_id
            and existing.get("status") in {"enabled", "websocket_connected"}
        )

    async def _get_existing(self, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.get(self.url, headers=self._headers(), timeout=10.0)
        if response.status_code != 200:
            raise RuntimeError(
                f"Could not list EventSub subscriptions (HTTP {response.status_code})."
            )
        return response.json()

    async def _find_after_conflict(
        self, client: httpx.AsyncClient, spec: dict[str, Any]
    ) -> Subscription | None:
        try:
            payload = await self._get_existing(client)
        except (httpx.HTTPError, RuntimeError, ValueError):
            return None
        for item in payload.get("data", []):
            if self._matches(item, spec):
                return self._as_subscription(item)
        return None

    def _safe_error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or ""
        except (ValueError, AttributeError):
            message = ""
        safe = str(message)
        for value in (
            self.settings.twitch_user_access_token,
            self.settings.twitch_client_secret,
            self.settings.twitch_refresh_token,
        ):
            if value:
                safe = safe.replace(value, "[REDACTED]")
        return safe or "Twitch did not provide an error message."

    async def create_for_session(self, session_id: str) -> list[Subscription]:
        """List, reuse, and create subscriptions for the current WebSocket session."""
        self._session_id = session_id
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient()
        try:
            existing_payload = await self._get_existing(client)
            existing_items = existing_payload.get("data", [])
            current_cost = int(
                existing_payload.get(
                    "total_cost",
                    sum(
                        int(item.get("cost", SUBSCRIPTION_COST))
                        for item in existing_items
                        if item.get("status") in {"enabled", "websocket_connected"}
                    ),
                )
            )
            cost_limit = int(existing_payload.get("max_total_cost", MAX_TOTAL_COST))
            created_or_reused: list[Subscription] = []

            for spec in self._specs():
                current = next(
                    (item for item in existing_items if self._matches(item, spec)),
                    None,
                )
                if current is not None:
                    record = self._as_subscription(current)
                    created_or_reused.append(record)
                    logger.info(
                        "EventSub %s: reused %s subscription (cost %s).",
                        spec["type"],
                        record.status,
                        record.cost,
                    )
                    continue

                if current_cost + SUBSCRIPTION_COST > min(cost_limit, MAX_TOTAL_COST):
                    record = Subscription(
                        id="", type=spec["type"], status="cost_limit", cost=0
                    )
                    created_or_reused.append(record)
                    logger.error(
                        "Skipping EventSub %s: creating it would exceed total cost %s.",
                        spec["type"],
                        min(cost_limit, MAX_TOTAL_COST),
                    )
                    continue

                response = await client.post(
                    self.url, headers=self._headers(), json=spec, timeout=10.0
                )
                if response.status_code in {200, 202}:
                    data = response.json().get("data", [])
                    item = data[0] if data else {}
                    record = self._as_subscription(
                        {
                            **item,
                            "type": item.get("type", spec["type"]),
                            "status": item.get("status", "enabled"),
                            "cost": item.get("cost", SUBSCRIPTION_COST),
                        }
                    )
                    created_or_reused.append(record)
                    existing_items.append(item)
                    current_cost += record.cost
                    logger.info(
                        "EventSub %s: created %s subscription (cost %s).",
                        spec["type"],
                        record.status,
                        record.cost,
                    )
                    continue

                if response.status_code == 409:
                    record = await self._find_after_conflict(client, spec)
                    if record is None:
                        record = Subscription(
                            id="", type=spec["type"], status="already_exists", cost=0
                        )
                    else:
                        current_cost += record.cost
                    created_or_reused.append(record)
                    logger.info(
                        "EventSub %s: reused subscription after HTTP 409.",
                        spec["type"],
                    )
                    continue

                message = self._safe_error_message(response)
                if response.status_code in {400, 401, 403}:
                    logger.error(
                        "EventSub %s subscription rejected (HTTP %s): %s",
                        spec["type"],
                        response.status_code,
                        message,
                    )
                else:
                    logger.error(
                        "EventSub %s subscription failed (HTTP %s): %s",
                        spec["type"],
                        response.status_code,
                        message,
                    )
                created_or_reused.append(
                    Subscription(
                        id="", type=spec["type"], status=f"error_{response.status_code}", cost=0
                    )
                )

            self.subscriptions = created_or_reused
            return list(created_or_reused)
        finally:
            if owns_client:
                await client.aclose()
