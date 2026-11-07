"""Tests for required configuration and boolean validation."""

import pytest

from streamcrew.config import load_config


def test_missing_required_values_are_named(monkeypatch, tmp_path):
    for name in (
        "TWITCH_CLIENT_ID",
        "TWITCH_USER_ACCESS_TOKEN",
        "TWITCH_BROADCASTER_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="TWITCH_CLIENT_ID"):
        load_config(tmp_path / "missing.env")


def test_invalid_dry_run_value_is_rejected(monkeypatch, tmp_path):
    for name in (
        "TWITCH_CLIENT_ID",
        "TWITCH_USER_ACCESS_TOKEN",
        "TWITCH_BROADCASTER_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "TWITCH_CLIENT_ID=test-client\n"
        "TWITCH_USER_ACCESS_TOKEN=test-token\n"
        "TWITCH_BROADCASTER_ID=test-broadcaster\n"
        "DRY_RUN=maybe\n"
    )

    with pytest.raises(ValueError, match="DRY_RUN"):
        load_config(env_file)


def test_defaults_to_dry_run(monkeypatch, tmp_path):
    for name in (
        "TWITCH_CLIENT_ID",
        "TWITCH_USER_ACCESS_TOKEN",
        "TWITCH_BROADCASTER_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "TWITCH_CLIENT_ID=test-client\n"
        "TWITCH_USER_ACCESS_TOKEN=test-token\n"
        "TWITCH_BROADCASTER_ID=test-broadcaster\n"
    )

    settings = load_config(env_file)

    assert settings.dry_run is True
