"""Send allow-listed Twitch actions through one guarded Helix entry point."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from .rules import ACTION_ALLOWLIST, APPROVAL_ONLY_ACTIONS

logger = logging.getLogger(__name__)
HELIX_BASE = "https://api.twitch.tv/helix"


class ActionError(RuntimeError):
    """A guarded action could not be validated or Twitch rejected the request."""


def record_marker_result(
    store: Any, action: dict[str, Any], result: dict[str, Any], source: str
) -> bool:
    """Add a successful marker result to the local event feed for the overlay."""
    if (
        action.get("action") != "create_marker"
        or not isinstance(result, dict)
        or result.get("status") != "sent"
    ):
        return False
    data = result.get("data")
    markers = data.get("data", []) if isinstance(data, dict) else []
    marker = markers[0] if markers and isinstance(markers[0], dict) else {}
    marker_id = str(marker.get("id") or uuid.uuid4().hex)
    payload = {
        "action": "create_marker",
        "status": "sent",
        "source": source,
        "description": marker.get("description") or action.get("description", ""),
        "marker": marker,
    }
    return store.save_event(
        f"marker:{marker_id}", "action", "marker.created", payload
    )


def _required(action: dict[str, Any], name: str) -> str:
    value = action.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ActionError(f"Action requires a non-empty {name} value.")
    return value


def validate_action(action: Any) -> str:
    """Validate the allow-listed action and its documented request fields."""
    if not isinstance(action, dict):
        raise ActionError("Action must be an object.")
    action_name = action.get("action")
    if not isinstance(action_name, str) or action_name not in ACTION_ALLOWLIST:
        raise ActionError("Action is not in the supported allow-list.")
    fields = {
        "send_chat_message": {"action", "message"},
        "send_announcement": {"action", "message", "color"},
        "send_shoutout": {"action", "to_broadcaster_id"},
        "create_marker": {"action", "description"},
        "ban_user": {"action", "user_id", "reason", "duration"},
        "delete_message": {"action", "message_id"},
    }[action_name]
    if set(action) - fields:
        raise ActionError("Action contains unsupported fields.")

    if action_name in {"send_chat_message", "send_announcement"}:
        message = _required(action, "message")
        if len(message) > 500:
            raise ActionError("message must be at most 500 characters.")
    if action_name == "send_announcement":
        color = action.get("color", "primary")
        if not isinstance(color, str) or color not in {
            "primary", "blue", "green", "orange", "purple"
        }:
            raise ActionError("Announcement color must be primary, blue, green, orange, or purple.")
    elif action_name == "send_shoutout":
        _required(action, "to_broadcaster_id")
    elif action_name == "create_marker" and "description" in action:
        description = _required(action, "description")
        if len(description) > 140:
            raise ActionError("description must be at most 140 characters.")
    elif action_name == "ban_user":
        _required(action, "user_id")
        reason = action.get("reason")
        if reason is not None and (not isinstance(reason, str) or len(reason) > 500):
            raise ActionError("reason must be a string of at most 500 characters.")
        duration = action.get("duration")
        if duration is not None and (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or not 1 <= duration <= 1_209_600
        ):
            raise ActionError("duration must be between 1 and 1209600 seconds.")
    elif action_name == "delete_message":
        _required(action, "message_id")
    return action_name


def execute_action(
    action: dict[str, Any],
    mode: str,
    settings: Any,
    http_client: httpx.Client | None = None,
    *,
    approval_granted: bool = False,
) -> dict[str, Any]:
    """Run one approved action, or refuse it without making an HTTP request.

    ``http_client`` is only an injection point for mocked tests. Production use
    reads credentials from the settings object loaded by ``config.py``.
    """
    action_name = validate_action(action)
    if mode not in {"dry_run", "auto", "approve"}:
        raise ActionError("Action mode must be dry_run, approve, or auto.")
    dry_run = getattr(settings, "DRY_RUN", getattr(settings, "dry_run", True))
    if dry_run:
        logger.info("would do %s (DRY_RUN is enabled)", action_name or "action")
        return {"status": "dry_run"}
    if mode == "dry_run":
        logger.info("would do %s", action_name or "action")
        return {"status": "dry_run"}
    if action_name in APPROVAL_ONLY_ACTIONS and not (
        mode == "dry_run"
        or mode == "approve"
        or (mode == "auto" and approval_granted)
    ):
        raise ActionError(f"{action_name} can only run in approve mode.")

    broadcaster_id = settings.twitch_broadcaster_id
    moderator_id = broadcaster_id
    params: dict[str, str] | None = None
    body: dict[str, Any] | None = None
    method = "POST"
    endpoint = ""

    if action_name == "send_chat_message":
        endpoint = f"{HELIX_BASE}/chat/messages"
        body = {
            "broadcaster_id": broadcaster_id,
            "sender_id": broadcaster_id,
            "message": _required(action, "message"),
        }
    elif action_name == "send_announcement":
        endpoint = f"{HELIX_BASE}/chat/announcements"
        params = {"broadcaster_id": broadcaster_id, "moderator_id": moderator_id}
        body = {
            "message": _required(action, "message"),
            "color": action.get("color", "primary"),
        }
    elif action_name == "send_shoutout":
        endpoint = f"{HELIX_BASE}/chat/shoutouts"
        params = {
            "from_broadcaster_id": broadcaster_id,
            "to_broadcaster_id": _required(action, "to_broadcaster_id"),
            "moderator_id": moderator_id,
        }
    elif action_name == "create_marker":
        endpoint = f"{HELIX_BASE}/streams/markers"
        body = {"user_id": broadcaster_id}
        if "description" in action:
            body["description"] = _required(action, "description")
    elif action_name == "ban_user":
        endpoint = f"{HELIX_BASE}/moderation/bans"
        params = {"broadcaster_id": broadcaster_id, "moderator_id": moderator_id}
        data: dict[str, Any] = {"user_id": _required(action, "user_id")}
        if "reason" in action:
            data["reason"] = _required(action, "reason")
        if "duration" in action:
            data["duration"] = action["duration"]
        body = {"data": data}
    elif action_name == "delete_message":
        endpoint = f"{HELIX_BASE}/moderation/chat"
        params = {
            "broadcaster_id": broadcaster_id,
            "moderator_id": moderator_id,
            # Require a specific message ID to prevent clearing the whole chat.
            "message_id": _required(action, "message_id"),
        }
        method = "DELETE"

    headers = {
        "Authorization": f"Bearer {settings.twitch_user_access_token}",
        "Client-Id": settings.twitch_client_id,
    }
    if http_client is None:
        with httpx.Client(timeout=10.0) as client:
            response = client.request(
                method, endpoint, headers=headers, params=params, json=body
            )
    else:
        response = http_client.request(
            method, endpoint, headers=headers, params=params, json=body
        )

    if action_name == "send_shoutout" and response.status_code == 429:
        retry_time = response.headers.get("Ratelimit-Reset") or response.headers.get(
            "Retry-After", "unknown"
        )
        logger.warning("Shoutout was rate limited; retry time: %s. Not retrying.", retry_time)
    elif action_name == "create_marker" and 400 <= response.status_code < 500:
        logger.warning(
            "Stream marker was rejected with HTTP %s (the stream may be offline).",
            response.status_code,
        )

    if not response.is_success:
        raise ActionError(f"Twitch action {action_name} failed with HTTP {response.status_code}.")
    response_data = None if response.status_code == 204 else response.json()
    if action_name == "send_chat_message" and isinstance(response_data, dict):
        results = response_data.get("data", [])
        if results and isinstance(results[0], dict) and results[0].get("is_sent") is False:
            raise ActionError("Twitch accepted the chat request but did not send the message.")
    return {"status": "sent", "status_code": response.status_code, "data": response_data}
