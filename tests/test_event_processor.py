"""Integration tests for the EventSub-to-rules processing path."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from streamcrew.event_processor import EventProcessor
from streamcrew.eventsub import EventSubClient
from streamcrew.storage import SQLiteEventStore


def test_saved_raid_notification_runs_matching_rule_in_dry_run(tmp_path):
    settings = SimpleNamespace(
        dry_run=True,
        twitch_broadcaster_id="broadcaster-1",
        twitch_client_id="client-id",
        twitch_user_access_token="unused-test-token",
    )
    rule = {
        "id": "raid-thanks",
        "event": "channel.raid",
        "conditions": {"viewers": {"gte": 10}},
        "actions": [
            {
                "action": "send_shoutout",
                "to_broadcaster_id": "{{from_broadcaster_user_id}}",
            }
        ],
        "cooldown_seconds": 60,
        "mode": "auto",
    }
    notification = {
        "metadata": {
            "message_type": "notification",
            "subscription_type": "channel.raid",
        },
        "payload": {
            "event": {"viewers": 25, "from_broadcaster_user_id": "raider-1"}
        },
    }

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        processor = EventProcessor(settings, store, [rule])
        results = processor.process_notification(notification)

    assert len(results) == 1
    assert results[0]["status"] == "auto"
    assert results[0]["result"] == {"status": "dry_run"}


def test_fresh_eventsub_notification_reaches_processor_through_client(tmp_path):
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    settings = SimpleNamespace(
        dry_run=True,
        twitch_broadcaster_id="broadcaster-1",
        twitch_client_id="client-id",
        twitch_user_access_token="unused-test-token",
    )
    rule = {
        "id": "raid-thanks",
        "event": "channel.raid",
        "conditions": {"viewers": {"gte": 10}},
        "actions": [
            {
                "action": "send_shoutout",
                "to_broadcaster_id": "{{from_broadcaster_user_id}}",
            }
        ],
        "cooldown_seconds": 60,
        "mode": "auto",
    }
    frame = json.dumps(
        {
            "metadata": {
                "message_id": "wired-raid-1",
                "message_type": "notification",
                "message_timestamp": "2026-10-27T11:59:00Z",
                "subscription_type": "channel.raid",
            },
            "payload": {
                "event": {"viewers": 25, "from_broadcaster_user_id": "raider-1"}
            },
        }
    )

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        processor = EventProcessor(settings, store, [rule], clock=lambda: now)
        client = EventSubClient(
            SimpleNamespace(eventsub_ws_url="ws://example.test/ws"),
            store,
            clock=lambda: now,
            notification_callback=processor.process_notification,
        )

        assert client.handle_message(frame) is True
        assert client.handle_message(frame) is False
        assert store.get_rule_cooldown("raid-thanks") == now.isoformat()
        assert len(store.list_events()) == 1


def test_spam_burst_creates_one_grouped_pending_approval_and_calls_no_network(tmp_path):
    """Step 2 (R4): Detector firing writes one grouped approval (cap 25) and makes zero Helix calls."""
    settings = SimpleNamespace(
        dry_run=True,
        spam_min_accounts=5,
        spam_window_seconds=10,
        spam_cooldown_seconds=60,
        spam_timeout_seconds=600,
        group_cap=25,
    )
    network_calls = []

    def forbid_network(*args, **kwargs):
        network_calls.append((args, kwargs))
        raise AssertionError("No Twitch call should be made when queueing spam approval")

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        processor = EventProcessor(
            settings, store, rules=[], action_executor=forbid_network
        )
        for i in range(1, 31):
            msg = {
                "metadata": {
                    "message_id": f"burst-{i}",
                    "message_type": "notification",
                    "subscription_type": "channel.chat.message",
                    "message_timestamp": f"2026-11-05T12:00:0{i // 4}.{i % 4}00Z",
                },
                "payload": {
                    "event": {
                        "chatter_user_id": f"bot-{i}",
                        "chatter_user_login": f"bot_login_{i}",
                        "message": {"text": "CHEAP VIEWERS NOW!!! https://spam.example/x"},
                    }
                },
            }
            processor.process_notification(msg)

        pending = store.list_approvals("pending")

    assert network_calls == []
    assert len(pending) == 1
    assert pending[0]["rule_id"] == "spam-detector"
    action = json.loads(pending[0]["action_json"])
    assert action["action"] == "ban_user"
    assert action["duration"] == 600
    assert len(action["targets"]) == 25
    assert action["summary"]["accounts"] == 30
    assert action["summary"]["remaining_accounts"] == 5
    assert action["results"] == []
    assert "https://" not in action["summary"]["sample"]


def test_locked_approval_does_not_merge_subsequent_burst_accounts(tmp_path):
    """When an approval has been shown/locked, new spam messages create a separate approval."""
    settings = SimpleNamespace(
        dry_run=True,
        spam_min_accounts=2,
        spam_window_seconds=10,
        spam_cooldown_seconds=60,
        spam_timeout_seconds=600,
        group_cap=25,
    )

    def _make_msg(i, sec):
        return {
            "metadata": {
                "message_id": f"burst-msg-{i}",
                "subscription_type": "channel.chat.message",
                "message_timestamp": f"2026-11-05T12:00:0{sec}.000Z",
            },
            "payload": {
                "event": {
                    "chatter_user_id": f"bot-{i}",
                    "chatter_user_login": f"bot_login_{i}",
                    "message": {"text": "SPAM RAID WAVE"},
                }
            },
        }

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        processor = EventProcessor(settings, store, rules=[])
        processor.process_notification(_make_msg(1, 1))
        res = processor.process_notification(_make_msg(2, 2))
        assert len(res) == 1
        app_id_1 = res[0]["approval_id"]

        # Simulate human viewing: approval is marked locked
        first_row = store.get_approval(app_id_1)
        action_data = json.loads(first_row["action_json"])
        action_data["locked"] = True
        store.update_approval_status(app_id_1, "pending", action_json=action_data)

        # Continuing burst messages arrive
        processor.process_notification(_make_msg(3, 3))
        res_2 = processor.process_notification(_make_msg(4, 4))

        approvals = store.list_approvals("pending")
        # Ensure first approval wasn't mutated and a second approval was created
        assert len(approvals) == 2
        first_app = store.get_approval(app_id_1)
        first_action = json.loads(first_app["action_json"])
        assert len(first_action["targets"]) == 2


def test_rules_loader_dynamically_evaluates_shipped_rules(tmp_path):
    """EventProcessor reloads rules dynamically when rules_loader is provided."""
    settings = SimpleNamespace(dry_run=True)
    rule_list = []

    def loader():
        return list(rule_list)

    raid_msg = {
        "metadata": {
            "message_type": "notification",
            "subscription_type": "channel.raid",
        },
        "payload": {
            "event": {"viewers": 15, "from_broadcaster_user_id": "raider-1"}
        },
    }

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        processor = EventProcessor(settings, store, rules_loader=loader)
        # Initially empty rules -> no matches
        assert processor.process_notification(raid_msg) == []

        # Shipped rule added to loader output
        rule_list.append({
            "id": "new-raid-rule",
            "event": "channel.raid",
            "conditions": {"viewers": {"gte": 10}},
            "actions": [{"action": "send_shoutout", "to_broadcaster_id": "raider-1"}],
            "cooldown_seconds": 60,
            "mode": "auto",
        })

        # Next event immediately picks up the new rule without restarting
        outcomes = processor.process_notification(raid_msg)
        assert len(outcomes) == 1
        assert outcomes[0]["status"] == "auto"
        assert outcomes[0]["action"]["action"] == "send_shoutout"
