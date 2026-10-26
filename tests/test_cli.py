"""Exercise approval CLI commands against temporary storage and dry-run config."""

from types import SimpleNamespace

from streamcrew import cli
from streamcrew.storage import SQLiteEventStore


def test_cli_reject_records_decision_in_local_database(tmp_path, monkeypatch, capsys):
    database = tmp_path / "events.sqlite3"
    with SQLiteEventStore(database) as store:
        approval_id = store.save_approval(
            "cli-test", {"action": "send_chat_message", "message": "hello"}
        )
    monkeypatch.setattr(cli, "_default_database_path", lambda: database)

    assert cli.main(["reject", str(approval_id)]) == 0
    assert f"approval {approval_id}: rejected" in capsys.readouterr().out
    with SQLiteEventStore(database) as store:
        assert store.get_approval(approval_id)["status"] == "rejected"


def test_cli_approve_stays_dry_run_in_local_database(tmp_path, monkeypatch, capsys):
    database = tmp_path / "events.sqlite3"
    with SQLiteEventStore(database) as store:
        approval_id = store.save_approval(
            "cli-test", {"action": "send_chat_message", "message": "hello"}
        )
    monkeypatch.setattr(cli, "_default_database_path", lambda: database)
    monkeypatch.setattr(cli, "load_config", lambda: SimpleNamespace(dry_run=True))

    assert cli.main(["approve", str(approval_id)]) == 0
    assert f"approval {approval_id}: failed" in capsys.readouterr().out
    with SQLiteEventStore(database) as store:
        row = store.get_approval(approval_id)
    assert row["status"] == "failed"
    assert row["decided_by"] == "cli"
