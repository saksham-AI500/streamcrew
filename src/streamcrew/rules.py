"""Load and validate simple JSON automation rules for StreamCrew."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

ACTION_ALLOWLIST = frozenset(
    {
        "send_chat_message",
        "send_announcement",
        "send_shoutout",
        "create_marker",
        "ban_user",
        "delete_message",
    }
)
APPROVAL_ONLY_ACTIONS = frozenset({"ban_user", "delete_message"})
RULE_MODES = frozenset({"dry_run", "approve", "auto"})
_TEMPLATE_FIELD = re.compile(r"{{\s*([\w.]+)\s*}}")


class RuleValidationError(ValueError):
    """Raised when a rule file does not follow the supported JSON format."""


def validate_rule(rule: Any) -> dict[str, Any]:
    """Validate a rule and return it with safe default settings applied."""
    if not isinstance(rule, dict):
        raise RuleValidationError("A rule must be a JSON object.")

    normalized = dict(rule)
    errors: list[str] = []
    for field in ("id", "event"):
        if not isinstance(rule.get(field), str) or not rule[field].strip():
            errors.append(f"{field} must be a non-empty string")

    conditions = rule.get("conditions", {})
    if not isinstance(conditions, dict):
        errors.append("conditions must be an object")
    else:
        for field, expected in conditions.items():
            if not isinstance(field, str) or not field:
                errors.append("condition field names must be non-empty strings")
                continue
            if isinstance(expected, dict):
                if not expected or not set(expected).issubset({"gte", "lte"}):
                    errors.append(f"condition {field} supports only gte and lte")
                    continue
                for operator, value in expected.items():
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                    ):
                        errors.append(f"condition {field}.{operator} must be numeric")

    cooldown = rule.get("cooldown_seconds", 0)
    if isinstance(cooldown, bool) or not isinstance(cooldown, int) or cooldown < 0:
        errors.append("cooldown_seconds must be a non-negative integer")

    mode = rule.get("mode", "dry_run")
    if not isinstance(mode, str) or mode not in RULE_MODES:
        errors.append("mode must be dry_run, approve, or auto")
    normalized["mode"] = mode

    actions = rule.get("actions")
    if not isinstance(actions, list) or not actions:
        errors.append("actions must be a non-empty array")
    else:
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                errors.append(f"actions[{index}] must be an object")
                continue
            action_type = action.get("action")
            if not isinstance(action_type, str) or action_type not in ACTION_ALLOWLIST:
                errors.append(f"actions[{index}] has an unsupported action")
            elif action_type in APPROVAL_ONLY_ACTIONS and mode != "approve":
                errors.append(
                    f"actions[{index}] {action_type} requires mode approve"
                )

    if errors:
        raise RuleValidationError("; ".join(errors))
    normalized["conditions"] = conditions
    normalized["cooldown_seconds"] = cooldown
    normalized["actions"] = actions
    return normalized


def load_rule(path: str | Path) -> dict[str, Any]:
    """Read a rule JSON file and validate its contents."""
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuleValidationError(f"Could not read rule JSON: {error}") from error
    return validate_rule(raw)


def _get_field(payload: dict[str, Any], field: str) -> Any:
    value: Any = payload
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def conditions_match(conditions: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Return whether every equality or numeric range condition matches."""
    for field, expected in conditions.items():
        actual = _get_field(payload, field)
        if isinstance(expected, dict):
            if isinstance(actual, bool) or not isinstance(actual, (int, float)):
                return False
            if "gte" in expected and actual < expected["gte"]:
                return False
            if "lte" in expected and actual > expected["lte"]:
                return False
        elif actual != expected:
            return False
    return True


def render_value(value: Any, payload: dict[str, Any]) -> Any:
    """Replace template placeholders recursively using event fields."""
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            result = _get_field(payload, match.group(1))
            if result is None:
                raise RuleValidationError(
                    f"Template field {match.group(1)} is missing from the event."
                )
            return str(result)

        return _TEMPLATE_FIELD.sub(replace, value)
    if isinstance(value, list):
        return [render_value(item, payload) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, payload) for key, item in value.items()}
    return value
