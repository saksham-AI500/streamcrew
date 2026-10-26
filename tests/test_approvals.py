"""Check approval decisions and their guarded action execution behavior."""

import pytest

from streamcrew.approvals import ApprovalError, ApprovalQueue
from streamcrew.storage import SQLiteEventStore


class Settings:
    """Test settings that let the mocked action path run."""

    dry_run = False


def _pending(store, action=None):
    return store.save_approval(
        "test-rule", action or {"action": "send_chat_message", "message": "hello"}
    )


def test_item_remains_pending_until_approved(tmp_path):
    """Listing does not mutate a queued approval."""
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = _pending(store)
        queue = ApprovalQueue(store, Settings(), action_executor=lambda *_args, **_kw: pytest.fail("called"))

        assert queue.list()[0]["status"] == "pending"
        assert store.get_approval(approval_id)["status"] == "pending"


def test_reject_never_calls_action_layer(tmp_path):
    """Reject records the CLI decision without sending the action."""
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = _pending(store)

        def unexpected(*args, **kwargs):
            pytest.fail("rejected action reached the action layer")

        result = ApprovalQueue(store, Settings(), action_executor=unexpected).reject(approval_id)
        row = store.get_approval(approval_id)

    assert result["status"] == "rejected"
    assert row["status"] == "rejected"
    assert row["decided_by"] == "cli"
    assert row["decided_at"]


def test_approve_executes_once_and_marks_done(tmp_path):
    """An approved item goes through the action layer once with trusted approval."""
    calls = []

    def mocked_executor(action, mode, settings, **kwargs):
        calls.append((action, mode, settings, kwargs))
        return {"status": "sent", "status_code": 200}

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = _pending(store)
        queue = ApprovalQueue(store, Settings(), action_executor=mocked_executor)
        result = queue.approve(approval_id)
        row = store.get_approval(approval_id)

    assert result["status"] == "done"
    assert row["status"] == "done"
    assert row["decided_by"] == "cli"
    assert row["decided_at"]
    assert len(calls) == 1
    assert calls[0][1] == "auto"
    assert calls[0][3] == {"approval_granted": True}


def test_moderation_action_can_only_run_after_approval(tmp_path):
    """Ban actions saved as pending are executed only after the queue decision."""
    calls = []

    def mocked_executor(action, mode, settings, **kwargs):
        calls.append((action, mode, kwargs))
        return {"status": "sent", "status_code": 200}

    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = _pending(store, {"action": "ban_user", "user_id": "viewer-id"})
        queue = ApprovalQueue(store, Settings(), action_executor=mocked_executor)
        queue.approve(approval_id)

    assert len(calls) == 1
    assert calls[0][0] == {"action": "ban_user", "user_id": "viewer-id"}
    assert calls[0][1:] == ("auto", {"approval_granted": True})


def test_approved_marker_is_recorded_for_the_overlay(tmp_path):
    """A successful approved marker appears in the local marker event feed."""
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = _pending(
            store, {"action": "create_marker", "description": "Approved moment"}
        )
        queue = ApprovalQueue(
            store,
            Settings(),
            action_executor=lambda *_args, **_kwargs: {
                "status": "sent",
                "data": {"data": [{"id": "approved-marker", "description": "Approved moment"}]},
            },
        )
        result = queue.approve(approval_id)
        marker_events = [
            item for item in store.list_events()
            if item["subscription_type"] == "marker.created"
        ]

    assert result["status"] == "done"
    assert len(marker_events) == 1
    assert marker_events[0]["message_id"] == "marker:approved-marker"


def test_approval_cannot_be_decided_twice(tmp_path):
    """A resolved row cannot be approved or rejected a second time."""
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = _pending(store)
        queue = ApprovalQueue(store, Settings(), action_executor=lambda *_a, **_k: {"status": "sent"})
        queue.reject(approval_id)
        with pytest.raises(ApprovalError, match="no longer pending"):
            queue.approve(approval_id)
