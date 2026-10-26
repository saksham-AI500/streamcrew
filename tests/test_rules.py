"""Tests for the supported rule format and event condition matching."""

import pytest

from streamcrew.rules import (
    RuleValidationError,
    conditions_match,
    render_value,
    validate_rule,
)


def test_valid_rule_defaults_to_dry_run():
    rule = validate_rule(
        {
            "id": "welcome",
            "event": "channel.raid",
            "conditions": {"viewers": {"gte": 10}},
            "actions": [{"action": "send_shoutout"}],
            "cooldown_seconds": 30,
        }
    )

    assert rule["mode"] == "dry_run"


def test_invalid_action_is_rejected():
    with pytest.raises(RuleValidationError, match="unsupported action"):
        validate_rule(
            {
                "id": "bad",
                "event": "channel.raid",
                "actions": [{"action": "delete_channel"}],
            }
        )


def test_destructive_actions_require_approve_mode():
    with pytest.raises(RuleValidationError, match="requires mode approve"):
        validate_rule(
            {
                "id": "protect-chat",
                "event": "channel.chat.message",
                "actions": [{"action": "delete_message"}],
            }
        )


def test_conditions_support_equality_gte_and_lte():
    conditions = {
        "category": "Games",
        "viewers": {"gte": 10, "lte": 50},
    }

    assert conditions_match(conditions, {"category": "Games", "viewers": 27})
    assert not conditions_match(conditions, {"category": "Games", "viewers": 51})
    assert not conditions_match(conditions, {"category": "Music", "viewers": 27})


def test_template_variables_render_nested_event_fields():
    rendered = render_value(
        {
            "action": "send_shoutout",
            "to_broadcaster_id": "{{event.from_broadcaster_user_id}}",
        },
        {"event": {"from_broadcaster_user_id": "mock-friend-42"}},
    )

    assert rendered["to_broadcaster_id"] == "mock-friend-42"
