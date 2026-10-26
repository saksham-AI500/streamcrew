"""Mocked tests for EventSub subscription cost and conflict handling."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from streamcrew.subscriptions import SubscriptionManager


def _settings():
    return SimpleNamespace(
        eventsub_subscriptions_url="https://mock.test/helix/eventsub/subscriptions",
        twitch_user_access_token="test-access-value",
        twitch_client_id="test-client-id",
        twitch_client_secret="test-client-secret",
        twitch_refresh_token="test-refresh-value",
        twitch_broadcaster_id="12345",
    )


def _request_bodies():
    settings = _settings()
    posted = []

    async def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"data": [], "total_cost": 0, "max_total_cost": 10},
            )
        body = json.loads(request.content)
        posted.append(body)
        return httpx.Response(
            202,
            json={
                "data": [
                    {
                        **body,
                        "id": f"test-{len(posted)}",
                        "status": "enabled",
                        "cost": 0,
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            manager = SubscriptionManager(settings, http_client=client)
            await manager.create_for_session("session-body-check")

    asyncio.run(run())
    return posted


def test_all_six_subscription_request_bodies():
    assert _request_bodies() == [
        {
            "type": "stream.online",
            "version": "1",
            "condition": {"broadcaster_user_id": "12345"},
            "transport": {
                "method": "websocket",
                "session_id": "session-body-check",
            },
        },
        {
            "type": "stream.offline",
            "version": "1",
            "condition": {"broadcaster_user_id": "12345"},
            "transport": {
                "method": "websocket",
                "session_id": "session-body-check",
            },
        },
        {
            "type": "channel.chat.message",
            "version": "1",
            "condition": {
                "broadcaster_user_id": "12345",
                "user_id": "12345",
            },
            "transport": {
                "method": "websocket",
                "session_id": "session-body-check",
            },
        },
        {
            "type": "channel.raid",
            "version": "1",
            "condition": {"to_broadcaster_user_id": "12345"},
            "transport": {
                "method": "websocket",
                "session_id": "session-body-check",
            },
        },
        {
            "type": "channel.follow",
            "version": "2",
            "condition": {
                "broadcaster_user_id": "12345",
                "moderator_user_id": "12345",
            },
            "transport": {
                "method": "websocket",
                "session_id": "session-body-check",
            },
        },
        {
            "type": "channel.chat.notification",
            "version": "1",
            "condition": {
                "broadcaster_user_id": "12345",
                "user_id": "12345",
            },
            "transport": {
                "method": "websocket",
                "session_id": "session-body-check",
            },
        },
    ]


@pytest.mark.parametrize(
    "chat_type",
    ("channel.chat.message", "channel.chat.notification"),
)
def test_chat_subscriptions_use_v1_user_read_chat_body(chat_type):
    chat_requests = [
        body
        for body in _request_bodies()
        if body["type"] in {"channel.chat.message", "channel.chat.notification"}
    ]
    body = next(item for item in chat_requests if item["type"] == chat_type)

    assert body["version"] == "1"
    assert body["condition"] == {
        "broadcaster_user_id": "12345",
        "user_id": "12345",
    }
    assert body["transport"] == {
        "method": "websocket",
        "session_id": "session-body-check",
    }


def test_cost_limit_prevents_subscriptions_over_ten():
    posted = []

    async def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"data": [], "total_cost": 9, "max_total_cost": 10},
            )
        posted.append(json.loads(request.content))
        spec = json.loads(request.content)
        return httpx.Response(
            202,
            json={
                "data": [
                    {
                        **spec,
                        "id": "created-subscription",
                        "status": "enabled",
                        "cost": 1,
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            manager = SubscriptionManager(_settings(), http_client=client)
            return await manager.create_for_session("session-cost")

    records = asyncio.run(run())

    assert len(posted) == 1
    assert records[0].status == "enabled"
    assert sum(record.status == "cost_limit" for record in records) == 5


def test_conflict_reuses_existing_subscription():
    get_count = 0
    post_count = 0
    reused = {
        "id": "existing-subscription",
        "type": "stream.online",
        "version": "1",
        "condition": {"broadcaster_user_id": "12345"},
        "transport": {"method": "websocket", "session_id": "session-409"},
        "status": "enabled",
        "cost": 1,
    }

    async def handler(request):
        nonlocal get_count, post_count
        if request.method == "GET":
            get_count += 1
            data = [reused] if get_count > 1 else []
            return httpx.Response(
                200,
                json={"data": data, "total_cost": len(data), "max_total_cost": 10},
            )
        post_count += 1
        if post_count == 1:
            return httpx.Response(409, json={"message": "already exists"})
        spec = json.loads(request.content)
        return httpx.Response(
            202,
            json={
                "data": [
                    {
                        **spec,
                        "id": f"created-{post_count}",
                        "status": "enabled",
                        "cost": 1,
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            manager = SubscriptionManager(_settings(), http_client=client)
            return await manager.create_for_session("session-409")

    records = asyncio.run(run())

    assert records[0].id == "existing-subscription"
    assert records[0].status == "enabled"
    assert get_count == 2
