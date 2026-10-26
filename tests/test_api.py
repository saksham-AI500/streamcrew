"""Test local API routes and approval-token protection without network access."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from streamcrew.api import create_app
from streamcrew.storage import SQLiteEventStore


def test_events_and_pending_approvals_are_readable(tmp_path):
    settings = SimpleNamespace(local_api_token="unit-test-local-key", dry_run=True)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        store.save_event("event-1", "notification", "stream.online", {"live": True})
        store.save_approval("rule-1", {"action": "send_chat_message", "message": "hello"})
        client = TestClient(create_app(store=store, settings=settings))

        event_response = client.get("/events?limit=10")
        approval_response = client.get("/approvals")
        overlay_response = client.get("/overlay")

    assert event_response.status_code == 200
    assert event_response.json()["events"][0]["payload"] == {"live": True}
    assert approval_response.status_code == 200
    assert approval_response.json()["approvals"][0]["status"] == "pending"
    assert overlay_response.status_code == 200
    assert "text/html" in overlay_response.headers["content-type"]
    assert "Markers created" in overlay_response.text
    assert '/approvals?status=pending' in overlay_response.text
    assert "LOCAL_API_TOKEN" not in overlay_response.text


def test_approval_changes_require_local_token(tmp_path):
    settings = SimpleNamespace(local_api_token="unit-test-local-key", dry_run=True)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = store.save_approval(
            "rule-1", {"action": "send_chat_message", "message": "hello"}
        )
        client = TestClient(create_app(store=store, settings=settings))

        missing = client.post(f"/approvals/{approval_id}/reject")
        wrong = client.post(
            f"/approvals/{approval_id}/reject",
            headers={"X-Local-Token": "wrong-test-key"},
        )
        correct = client.post(
            f"/approvals/{approval_id}/reject",
            headers={"X-Local-Token": "unit-test-local-key"},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert correct.status_code == 200
    assert correct.json()["status"] == "rejected"


def test_approved_api_action_uses_mock_executor(tmp_path):
    calls = []

    def mock_executor(action, mode, settings, **kwargs):
        calls.append((action, mode, kwargs))
        return {"status": "sent", "status_code": 200}

    settings = SimpleNamespace(local_api_token="unit-test-local-key", dry_run=False)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        approval_id = store.save_approval(
            "rule-1", {"action": "send_chat_message", "message": "hello"}
        )
        client = TestClient(
            create_app(store=store, settings=settings, action_executor=mock_executor)
        )
        response = client.post(
            f"/approvals/{approval_id}/approve",
            headers={"X-Local-Token": "unit-test-local-key"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert len(calls) == 1
    assert calls[0][1:] == ("auto", {"approval_granted": True})
