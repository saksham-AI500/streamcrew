"""Ensure the setup helper reports presence without revealing credential values."""

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_check_setup():
    spec = importlib.util.spec_from_file_location(
        "streamcrew_check_setup", PROJECT_ROOT / "scripts" / "check_setup.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_report_never_prints_credential_values(capsys):
    module = _load_check_setup()
    secret_value = "abcd1234-sensitive-value"

    module._report_setting("TWITCH_USER_ACCESS_TOKEN", secret_value)
    module._report_setting("TWITCH_CLIENT_SECRET", secret_value)
    module._report_setting("TWITCH_BROADCASTER_ID", "")

    output = capsys.readouterr().out
    assert "TWITCH_USER_ACCESS_TOKEN: set" in output
    assert "TWITCH_CLIENT_SECRET: set" in output
    assert "TWITCH_BROADCASTER_ID: missing" in output
    assert "abcd" not in output
    assert secret_value not in output
