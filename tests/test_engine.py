"""Tests for rule cooldowns, dry-run behavior, and approval creation."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from streamcrew.actions import ActionError
from streamcrew.engine import RuleEngine
from streamcrew.rules import load_rule
from streamcrew.storage import SQLiteEventStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _rule(mode="dry_run"):
    return {
        "id": "raid-test",
        "event": "channel.raid",
        "conditions": {"viewers": {"gte": 10}},
        "actions": [
            {
                "action": "send_shoutout",
                "to_broadcaster_id": "{{from_broadcaster_user_id}}",
            }
        ],
        "cooldown_seconds": 60,
        "mode": mode,
    }


def test_dry_run_logs_would_do_and_creates_no_approval(tmp_path, caplog):
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        engine = RuleEngine(store, action_executor=lambda *_: pytest.fail("must not execute"))
        with caplog.at_level(logging.INFO):
            result = engine.run_rule(
                _rule(),
                "channel.raid",
                {"viewers": 27, "from_broadcaster_user_id": "mock-friend-42"},
            )

        assert result[0]["status"] == "dry_run"
        assert "would do send_shoutout" in caplog.text
        assert store.list_approvals() == []


def test_approve_mode_creates_pending_approval(tmp_path):
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        engine = RuleEngine(store)
        result = engine.run_rule(
            _rule(mode="approve"),
            "channel.raid",
            {"viewers": 27, "from_broadcaster_user_id": "mock-friend-42"},
        )

        approvals = store.list_approvals(status="pending")

    assert result[0]["status"] == "pending"
    assert len(approvals) == 1
    assert approvals[0]["rule_id"] == "raid-test"
    assert approvals[0]["status"] == "pending"
    assert json.loads(approvals[0]["action_json"])["to_broadcaster_id"] == "mock-friend-42"


def test_cooldown_is_persisted_and_blocks_second_run(tmp_path):
    now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    database = tmp_path / "events.sqlite3"
    payload = {"viewers": 27, "from_broadcaster_user_id": "mock-friend-42"}
    with SQLiteEventStore(database) as store:
        first_engine = RuleEngine(store, clock=lambda: now)
        assert first_engine.run_rule(_rule(), "channel.raid", payload)[0]["status"] == "dry_run"

    with SQLiteEventStore(database) as store:
        second_engine = RuleEngine(store, clock=lambda: now + timedelta(seconds=10))
        result = second_engine.run_rule(_rule(), "channel.raid", payload)

    assert result == [{"status": "cooldown", "rule_id": "raid-test"}]


def test_saved_raid_fixture_rule_runs_in_dry_run(tmp_path, caplog):
    rule = load_rule(PROJECT_ROOT / "rules" / "raid_shoutout.json")
    fixture = json.loads((PROJECT_ROOT / "fixtures" / "raid_event.json").read_text())
    event_type = fixture["metadata"]["subscription_type"]
    payload = fixture["payload"]["event"]

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        engine = RuleEngine(store)
        with caplog.at_level(logging.INFO):
            result = engine.run_rule(rule, event_type, payload)

    assert result[0]["status"] == "dry_run"
    assert "would do send_shoutout" in caplog.text
    assert "mock-friend-42" not in caplog.text


def test_dry_run_log_does_not_include_rendered_chat_content(tmp_path, caplog):
    rule = {
        "id": "chat-echo-test",
        "event": "channel.chat.message",
        "actions": [
            {"action": "send_chat_message", "message": "{{message.text}}"}
        ],
        "cooldown_seconds": 0,
        "mode": "dry_run",
    }
    private_text = "private test message content"
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        engine = RuleEngine(store)
        with caplog.at_level(logging.INFO):
            result = engine.run_rule(
                rule,
                "channel.chat.message",
                {"message": {"text": private_text}},
            )

    assert result[0]["status"] == "dry_run"
    assert "would do send_chat_message" in caplog.text
    assert private_text not in caplog.text


def test_rule_engine_rejects_malformed_action_before_dry_run(tmp_path):
    rule = {
        "id": "invalid-chat-rule",
        "event": "channel.chat.message",
        "actions": [{"action": "send_chat_message"}],
        "cooldown_seconds": 0,
        "mode": "dry_run",
    }
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        engine = RuleEngine(store)
        with pytest.raises(ActionError, match="message"):
            engine.run_rule(rule, "channel.chat.message", {"text": "hello"})


def test_successful_marker_action_is_logged_for_the_overlay(tmp_path):
    rule = {
        "id": "marker-test",
        "event": "channel.chat.message",
        "actions": [{"action": "create_marker", "description": "Chat spike"}],
        "cooldown_seconds": 0,
        "mode": "auto",
    }
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        engine = RuleEngine(
            store,
            action_executor=lambda *_: {
                "status": "sent",
                "status_code": 200,
                "data": {"data": [{"id": "marker-123", "description": "Chat spike"}]},
            },
        )
        result = engine.run_rule(rule, "channel.chat.message", {"text": "wow"})
        markers = store.list_events(limit=10)

    assert result[0]["status"] == "auto"
    marker = next(event for event in markers if event["subscription_type"] == "marker.created")
    assert marker["message_id"] == "marker:marker-123"
    assert marker["payload"]["description"] == "Chat spike"


def test_failed_auto_action_does_not_consume_the_rule_cooldown(tmp_path):
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    payload = {"viewers": 27, "from_broadcaster_user_id": "mock-friend-42"}
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        failing_engine = RuleEngine(
            store,
            action_executor=lambda *_: (_ for _ in ()).throw(ActionError("failed")),
            clock=lambda: now,
        )
        with pytest.raises(ActionError, match="failed"):
            failing_engine.run_rule(_rule(mode="auto"), "channel.raid", payload)

        assert store.get_rule_cooldown("raid-test") is None

        retrying_engine = RuleEngine(
            store,
            action_executor=lambda *_: {"status": "sent"},
            clock=lambda: now,
        )
        result = retrying_engine.run_rule(_rule(mode="auto"), "channel.raid", payload)

    assert result[0]["status"] == "auto"


def test_successful_auto_action_records_the_rule_cooldown(tmp_path):
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    payload = {"viewers": 27, "from_broadcaster_user_id": "mock-friend-42"}
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        engine = RuleEngine(
            store,
            action_executor=lambda *_: {"status": "sent"},
            clock=lambda: now,
        )
        engine.run_rule(_rule(mode="auto"), "channel.raid", payload)

        assert store.get_rule_cooldown("raid-test") == now.isoformat()
