"""Small, read-only helpers for validating Twitch OAuth credentials."""

from __future__ import annotations

from typing import Any

import httpx


def validate_token(settings: Any) -> dict[str, Any]:
    """Validate the configured user token and report its public identity data."""
    response = httpx.get(
        "https://id.twitch.tv/oauth2/validate",
        headers={"Authorization": f"OAuth {settings.twitch_user_access_token}"},
        timeout=10.0,
    )
    if response.status_code == 401:
        raise ValueError("The Twitch user access token is invalid or expired.")
    if response.status_code != 200:
        raise RuntimeError(
            f"Twitch token validation failed with HTTP status {response.status_code}."
        )

    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("Twitch returned an invalid token validation response.")
    if result.get("client_id") != settings.twitch_client_id:
        raise ValueError("The validated token client_id does not match TWITCH_CLIENT_ID.")

    login = result.get("login", "")
    user_id = result.get("user_id", "")
    client_id = result.get("client_id", "")
    scopes = result.get("scopes", [])
    print(f"login: {login}")
    print(f"user_id: {user_id}")
    print(f"client_id: {client_id}")
    print(f"scopes: {', '.join(scopes) if isinstance(scopes, list) else scopes}")

    if str(user_id) != str(settings.twitch_broadcaster_id):
        print("WARNING: token user_id does not match TWITCH_BROADCASTER_ID.")

    return result
