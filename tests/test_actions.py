"""Exercise Twitch action request contracts without contacting Twitch."""

from __future__ import annotations

import httpx
import pytest

from streamcrew.actions import ActionError, execute_action


class Settings:
    """Small credential-shaped settings object for mocked requests."""

    twitch_client_id = "client-id"
    twitch_user_access_token = "test-token"
    twitch_broadcaster_id = "broadcaster-id"
    dry_run = False


@pytest.mark.parametrize(
    "action",
    [
        {"action": "send_chat_message", "message": "Hello"},
        {"action": "send_announcement", "message": "Starting soon"},
        {"action": "send_shoutout", "to_broadcaster_id": "friend-id"},
        {"action": "create_marker", "description": "Big moment"},
        {"action": "ban_user", "user_id": "viewer-id"},
        {"action": "delete_message", "message_id": "message-id"},
    ],
)
def test_dry_run_and_global_dry_run_make_zero_http_calls(action: dict) -> None:
    """Both dry-run gates stop every supported action before HTTP."""
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected HTTP request: {request.method} {request.url}")

    with httpx.Client(transport=httpx.MockTransport(unexpected_request)) as client:
        assert execute_action(action, "dry_run", Settings(), client)["status"] == "dry_run"
        assert execute_action(action, "auto", type("DrySettings", (), {
            "DRY_RUN": True,
            "twitch_broadcaster_id": "broadcaster-id",
            "twitch_user_access_token": "test-token",
            "twitch_client_id": "client-id",
        })(), client)["status"] == "dry_run"


@pytest.mark.parametrize(
    ("action", "method", "path", "expected_params", "expected_json"),
    [
        (
            {"action": "send_chat_message", "message": "Hello"},
            "POST",
            "/chat/messages",
            {},
            {"broadcaster_id": "broadcaster-id", "sender_id": "broadcaster-id", "message": "Hello"},
        ),
        (
            {"action": "send_announcement", "message": "Starting", "color": "purple"},
            "POST",
            "/chat/announcements",
            {"broadcaster_id": "broadcaster-id", "moderator_id": "broadcaster-id"},
            {"message": "Starting", "color": "purple"},
        ),
        (
            {"action": "send_shoutout", "to_broadcaster_id": "friend-id"},
            "POST",
            "/chat/shoutouts",
            {"from_broadcaster_id": "broadcaster-id", "to_broadcaster_id": "friend-id", "moderator_id": "broadcaster-id"},
            None,
        ),
        (
            {"action": "create_marker", "description": "Big moment"},
            "POST",
            "/streams/markers",
            {},
            {"user_id": "broadcaster-id", "description": "Big moment"},
        ),
        (
            {"action": "ban_user", "user_id": "viewer-id", "reason": "spam"},
            "POST",
            "/moderation/bans",
            {"broadcaster_id": "broadcaster-id", "moderator_id": "broadcaster-id"},
            {"data": {"user_id": "viewer-id", "reason": "spam"}},
        ),
        (
            {"action": "delete_message", "message_id": "message-id"},
            "DELETE",
            "/moderation/chat",
            {"broadcaster_id": "broadcaster-id", "moderator_id": "broadcaster-id", "message_id": "message-id"},
            None,
        ),
    ],
)
def test_actions_build_documented_helix_requests(
    action: dict,
    method: str,
    path: str,
    expected_params: dict,
    expected_json: dict | None,
) -> None:
    """Each supported action makes only its documented request via a mock."""
    def verify(request: httpx.Request) -> httpx.Response:
        assert request.method == method
        assert request.url.path == f"/helix{path}"
        assert dict(request.url.params) == expected_params
        assert request.headers["Client-Id"] == "client-id"
        assert request.headers["Authorization"] == "Bearer test-token"
        actual_json = request.read().decode() if request.content else None
        if expected_json is None:
            assert actual_json is None
        else:
            assert httpx.Response(200, content=actual_json).json() == expected_json
        return httpx.Response(200, json={"data": []})

    with httpx.Client(transport=httpx.MockTransport(verify)) as client:
        mode = "approve" if action["action"] in {"ban_user", "delete_message"} else "auto"
        result = execute_action(action, mode, Settings(), client)
    assert result["status"] == "sent"


@pytest.mark.parametrize("action_name", ["ban_user", "delete_message"])
def test_moderation_actions_require_approve_mode(action_name: str) -> None:
    """Ban and delete requests cannot run through ordinary auto mode."""
    action = (
        {"action": "ban_user", "user_id": "viewer-id"}
        if action_name == "ban_user"
        else {"action": "delete_message", "message_id": "message-id"}
    )
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("HTTP called"))) as client:
        with pytest.raises(ActionError, match="approve mode"):
            execute_action(action, "auto", Settings(), client)


def test_approved_moderation_request_can_use_auto_mode() -> None:
    """The approval queue's private approval marker unlocks auto execution."""
    seen = []

    def capture(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    action = {"action": "ban_user", "user_id": "viewer-id"}
    with httpx.Client(transport=httpx.MockTransport(capture)) as client:
        result = execute_action(
            action, "auto", Settings(), client, approval_granted=True
        )
    assert result["status"] == "sent"
    assert len(seen) == 1


def test_shoutout_429_is_logged_without_retry(caplog: pytest.LogCaptureFixture) -> None:
    """Rate-limited shoutouts report Twitch's reset value and are not retried."""
    calls = 0

    def rate_limited(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Ratelimit-Reset": "1234567890"})

    action = {"action": "send_shoutout", "to_broadcaster_id": "friend-id"}
    with httpx.Client(transport=httpx.MockTransport(rate_limited)) as client:
        with pytest.raises(ActionError, match="HTTP 429"):
            execute_action(action, "auto", Settings(), client)
    assert calls == 1
    assert "1234567890" in caplog.text


def test_delete_requires_specific_message_to_avoid_clear_all() -> None:
    """The endpoint's optional message_id is required locally for safe use."""
    action = {"action": "delete_message"}
    with pytest.raises(ActionError, match="message_id"):
        execute_action(action, "approve", Settings())
