"""Load StreamCrew settings from environment variables and a local .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime settings needed to connect StreamCrew to Twitch."""

    twitch_client_id: str
    twitch_user_access_token: str
    twitch_broadcaster_id: str
    dry_run: bool = True
    twitch_client_secret: str = ""
    twitch_refresh_token: str = ""
    local_api_token: str = ""
    env_file: Path | None = None
    eventsub_ws_url: str = "wss://eventsub.wss.twitch.tv/ws"
    eventsub_subscriptions_url: str = (
        "https://api.twitch.tv/helix/eventsub/subscriptions"
    )
    spam_min_accounts: int = 5
    spam_window_seconds: int = 10
    spam_cooldown_seconds: int = 60
    spam_timeout_seconds: int = 600
    group_cap: int = 25
    action_pacing_seconds: float = 0.5


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a number.") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def load_config(env_file: str | Path | None = None) -> Config:
    """Load settings, raising a clear error when a required value is absent.

    The access token is kept in memory only; this function never prints or logs
    it. ``DRY_RUN`` defaults to true when omitted.
    """
    resolved_env_file = (
        Path(env_file)
        if env_file is not None
        else Path(__file__).resolve().parents[2] / ".env"
    )
    if env_file is None and not resolved_env_file.exists():
        example_file = Path(__file__).resolve().parents[2] / ".env.example"
        if example_file.exists():
            resolved_env_file = example_file
    load_dotenv(dotenv_path=resolved_env_file, override=False)

    required = {
        "TWITCH_CLIENT_ID": os.getenv("TWITCH_CLIENT_ID"),
        "TWITCH_USER_ACCESS_TOKEN": os.getenv("TWITCH_USER_ACCESS_TOKEN"),
        "TWITCH_BROADCASTER_ID": os.getenv("TWITCH_BROADCASTER_ID"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        names = ", ".join(missing)
        raise ValueError(
            f"Missing required environment variable(s): {names}. "
            "Set them in .env or in your process environment."
        )

    dry_run_value = os.getenv("DRY_RUN", "true").strip().lower()
    if dry_run_value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ValueError("DRY_RUN must be a boolean value such as true or false.")

    return Config(
        twitch_client_id=required["TWITCH_CLIENT_ID"] or "",
        twitch_user_access_token=required["TWITCH_USER_ACCESS_TOKEN"] or "",
        twitch_broadcaster_id=required["TWITCH_BROADCASTER_ID"] or "",
        dry_run=dry_run_value in {"true", "1", "yes", "on"},
        twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET", ""),
        twitch_refresh_token=os.getenv("TWITCH_REFRESH_TOKEN", ""),
        local_api_token=os.getenv("LOCAL_API_TOKEN", ""),
        env_file=resolved_env_file,
        eventsub_ws_url=os.getenv(
            "EVENTSUB_WS_URL", "wss://eventsub.wss.twitch.tv/ws"
        ),
        eventsub_subscriptions_url=os.getenv(
            "EVENTSUB_SUBSCRIPTIONS_URL",
            "https://api.twitch.tv/helix/eventsub/subscriptions",
        ),
        spam_min_accounts=_env_int("SPAM_MIN_ACCOUNTS", 5, minimum=1),
        spam_window_seconds=_env_int("SPAM_WINDOW_SECONDS", 10, minimum=1),
        spam_cooldown_seconds=_env_int("SPAM_COOLDOWN_SECONDS", 60, minimum=0),
        spam_timeout_seconds=_env_int("SPAM_TIMEOUT_SECONDS", 600, minimum=1),
        group_cap=_env_int("GROUP_CAP", 25, minimum=1),
        action_pacing_seconds=_env_float("ACTION_PACING_SECONDS", 0.5, minimum=0.0),
    )
