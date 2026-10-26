"""Tests for SQLite event storage and duplicate notification handling."""

from streamcrew.storage import SQLiteEventStore


def test_save_event_returns_false_for_duplicate_message_id(tmp_path):
    database_path = tmp_path / "events.sqlite3"

    with SQLiteEventStore(database_path) as store:
        payload = {"user_name": "example_viewer", "message": "hello"}

        assert store.save_event(
            "message-123", "notification", "channel.chat.message", payload
        ) is True
        assert store.save_event(
            "message-123", "notification", "channel.chat.message", payload
        ) is False


def test_store_creates_events_table(tmp_path):
    database_path = tmp_path / "events.sqlite3"

    with SQLiteEventStore(database_path) as store:
        columns = store._connection.execute("PRAGMA table_info(events)").fetchall()

    assert [column[1] for column in columns] == [
        "message_id",
        "message_type",
        "subscription_type",
        "received_at",
        "payload_json",
    ]


def test_list_events_returns_newest_first_with_decoded_payload(tmp_path):
    with SQLiteEventStore(tmp_path / "events.sqlite3") as store:
        store.save_event("first", "notification", "stream.online", {"n": 1})
        store.save_event("second", "notification", "stream.offline", {"n": 2})
        events = store.list_events(limit=1)

    assert len(events) == 1
    assert events[0]["message_id"] == "second"
    assert events[0]["payload"] == {"n": 2}
