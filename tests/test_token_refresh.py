"""Mocked tests for refresh-token exchange and local credential updates."""

from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

from streamcrew import token_refresh


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def test_refresh_success_updates_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TWITCH_USER_ACCESS_TOKEN=old-test-access\n"
        "TWITCH_REFRESH_TOKEN=old-test-refresh\n"
        "OTHER_SETTING=keep-me\n"
    )
    response_body = {
        "access_token": "new-test-access",
        "refresh_token": "new-test-refresh",
        "expires_in": 14400,
        "scope": ["user:read:chat"],
        "token_type": "bearer",
    }
    monkeypatch.setattr(
        token_refresh.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(200, response_body),
    )
    settings = SimpleNamespace(
        twitch_client_id="test-client-id",
        twitch_client_secret="test-client-secret",
        twitch_refresh_token="old-test-refresh",
        env_file=env_file,
    )

    result = token_refresh.refresh_user_token(settings)
    saved = dotenv_values(env_file)

    assert result == response_body
    assert saved["TWITCH_USER_ACCESS_TOKEN"] == "new-test-access"
    assert saved["TWITCH_REFRESH_TOKEN"] == "new-test-refresh"
    assert saved["OTHER_SETTING"] == "keep-me"


def test_refresh_400_requests_browser_login(tmp_path, monkeypatch):
    monkeypatch.setattr(
        token_refresh.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(400, {"message": "invalid grant"}),
    )
    settings = SimpleNamespace(
        twitch_client_id="test-client-id",
        twitch_client_secret="test-client-secret",
        twitch_refresh_token="old-test-refresh",
        env_file=tmp_path / ".env",
    )

    with pytest.raises(ValueError, match="redo the browser login"):
        token_refresh.refresh_user_token(settings)
