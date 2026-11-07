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

        missing_auth = client.get("/events?limit=10")
        event_response = client.get(
            "/events?limit=10", headers={"X-Local-Token": "unit-test-local-key"}
        )
        approval_response = client.get(
            "/approvals", headers={"X-Local-Token": "unit-test-local-key"}
        )
        overlay_events = client.get("/overlay/events?limit=10")
        overlay_approvals = client.get("/overlay/approvals")
        health_response = client.get("/health")
        overlay_response = client.get("/overlay")

    assert missing_auth.status_code == 401
    assert event_response.status_code == 200
    assert event_response.json()["events"][0]["payload"] == {"live": True}
    assert approval_response.status_code == 200
    assert approval_response.json()["approvals"][0]["status"] == "pending"
    assert overlay_events.status_code == 200
    assert "payload" not in overlay_events.json()["events"][0]
    assert overlay_approvals.status_code == 200
    assert "action_json" not in overlay_approvals.json()["approvals"][0]
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok", "service": "streamcrew"}
    assert overlay_response.status_code == 200
    assert "text/html" in overlay_response.headers["content-type"]
    assert "Markers created" in overlay_response.text
    assert '/overlay/approvals' in overlay_response.text
    assert '/overlay/events?limit=50' in overlay_response.text
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


def test_empty_database_returns_empty_overlay_summaries(tmp_path):
    settings = SimpleNamespace(local_api_token="unit-test-local-key", dry_run=True)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        client = TestClient(create_app(store=store, settings=settings))

        events = client.get("/overlay/events")
        approvals = client.get("/overlay/approvals")

    assert events.status_code == 200
    assert events.json() == {"events": []}
    assert approvals.status_code == 200
    assert approvals.json() == {"approvals": []}


def test_storage_failure_returns_service_unavailable_not_server_error(tmp_path):
    settings = SimpleNamespace(local_api_token="unit-test-local-key", dry_run=True)
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    client = TestClient(create_app(store=store, settings=settings))
    store.close()

    auth = {"X-Local-Token": "unit-test-local-key"}
    responses = [
        client.get("/health"),
        client.get("/events", headers=auth),
        client.get("/approvals", headers=auth),
        client.get("/overlay/events"),
        client.get("/overlay/approvals"),
        client.post("/approvals/1/approve", headers=auth),
        client.post("/approvals/1/reject", headers=auth),
    ]

    assert [response.status_code for response in responses] == [503] * len(responses)


def test_overlay_page_has_loading_and_unavailable_states(tmp_path):
    settings = SimpleNamespace(local_api_token="unit-test-local-key", dry_run=True)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        client = TestClient(create_app(store=store, settings=settings))
        page = client.get("/overlay").text

    assert "Loading recent events" in page
    assert "Loading markers" in page
    assert "Loading pending approvals" in page
    assert "Local crew unavailable; retrying" in page


def test_landing_page_serves_interactive_simulation(tmp_path):
    settings = SimpleNamespace(local_api_token="unit-test-local-key", dry_run=True)
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        client = TestClient(create_app(store=store, settings=settings))
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Interactive Incident Lifecycle" in response.text
    assert "The engine runs without Switch. The team workflow, roles, and approval gate do not." in response.text
    assert "LOCAL_API_TOKEN" not in response.text
