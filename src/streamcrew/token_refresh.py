"""Refresh a Twitch user token and save its replacement in the local env file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


def _replace_env_values(env_file: Path, replacements: dict[str, str]) -> None:
    """Replace selected env-file assignments without displaying their values."""
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    updated: list[str] = []
    written: set[str] = set()

    for line in lines:
        key, separator, _ = line.partition("=")
        normalized_key = key.strip()
        if separator and normalized_key in replacements:
            updated.append(f"{normalized_key}={replacements[normalized_key]}")
            written.add(normalized_key)
        else:
            updated.append(line)

    for key, value in replacements.items():
        if key not in written:
            updated.append(f"{key}={value}")

    env_file.write_text("\n".join(updated).rstrip("\n") + "\n")


def refresh_user_token(settings: Any) -> dict[str, Any]:
    """Exchange a refresh token for new credentials and persist both values."""
    client_id = settings.twitch_client_id
    client_secret = settings.twitch_client_secret
    refresh_token = settings.twitch_refresh_token
    if not client_secret or not refresh_token:
        raise ValueError("TWITCH_CLIENT_SECRET and TWITCH_REFRESH_TOKEN are required.")

    response = httpx.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10.0,
    )
    if response.status_code in {400, 401}:
        raise ValueError(
            "The refresh token is invalid; the user must redo the browser login."
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"Twitch token refresh failed with HTTP status {response.status_code}."
        )

    result = response.json()
    access_token = result.get("access_token")
    new_refresh_token = result.get("refresh_token")
    if not access_token or not new_refresh_token:
        raise ValueError("Twitch token refresh response is missing token values.")

    configured_path = getattr(settings, "env_file", None)
    env_file = Path(configured_path) if configured_path else Path(__file__).resolve().parents[2] / ".env"
    _replace_env_values(
        env_file,
        {
            "TWITCH_USER_ACCESS_TOKEN": access_token,
            "TWITCH_REFRESH_TOKEN": new_refresh_token,
        },
    )
    return result
