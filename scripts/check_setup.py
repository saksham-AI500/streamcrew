#!/usr/bin/env python3
"""Print a masked configuration summary and validate the Twitch user token."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from streamcrew.config import load_config  # noqa: E402
from streamcrew.twitch_auth import validate_token  # noqa: E402


def _report_setting(name: str, value: str, *, secret: bool = False) -> None:
    if not value:
        print(f"{name}: missing")
    elif secret:
        print(f"{name}: set ({value[:4]}…)")
    else:
        print(f"{name}: set")


def main() -> int:
    try:
        settings = load_config(PROJECT_ROOT / ".env")
        _report_setting("TWITCH_CLIENT_ID", settings.twitch_client_id, secret=True)
        _report_setting(
            "TWITCH_USER_ACCESS_TOKEN",
            settings.twitch_user_access_token,
            secret=True,
        )
        _report_setting("TWITCH_BROADCASTER_ID", settings.twitch_broadcaster_id)
        _report_setting("DRY_RUN", os.getenv("DRY_RUN", "true"))
        _report_setting(
            "TWITCH_CLIENT_SECRET", os.getenv("TWITCH_CLIENT_SECRET", ""), secret=True
        )

        result = validate_token(settings)
        print(
            "Validation: valid "
            f"(client_id matches; login={result.get('login', '')}; "
            f"user_id={result.get('user_id', '')})"
        )
        return 0
    except Exception as exc:
        # Exception messages from our validation path never include request headers.
        print(f"Setup check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
