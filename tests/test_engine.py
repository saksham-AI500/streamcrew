"""Tests for rule cooldowns, dry-run behavior, and approval creation."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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
    assert "mock-friend-42" in caplog.text


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
