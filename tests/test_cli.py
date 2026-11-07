"""Exercise approval CLI commands against temporary storage and dry-run config."""

from types import SimpleNamespace

import pytest

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


def test_cli_events_metadata_only_omits_message_body(
    tmp_path, monkeypatch, capsys
):
    database = tmp_path / "events.sqlite3"
    with SQLiteEventStore(database) as store:
        store.save_event(
            "msg-test",
            "notification",
            "channel.chat.message",
            {"event": {"message": {"text": "private chat body"}}},
        )
    monkeypatch.setattr(cli, "_default_database_path", lambda: database)

    assert cli.main(["events", "--limit", "1", "--metadata-only"]) == 0
    output = capsys.readouterr().out
    assert "channel.chat.message" in output
    assert "msg-test" in output
    assert "private chat body" not in output
    assert "payload" not in output


def test_cli_listen_reports_configuration_error(monkeypatch, capsys):
    async def fail():
        raise ValueError("Missing required environment variable(s): TWITCH_CLIENT_ID")

    monkeypatch.setattr(cli, "_listen", fail)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["listen"])

    assert exit_info.value.code == 1
    assert "Missing required environment variable" in capsys.readouterr().err


def test_cli_simulate_spam_and_approvals_list_shows_account_count_and_sample(
    tmp_path, monkeypatch, capsys
):
    """Steps 2 & 3 (R4 & R6): crew simulate spam queues one grouped approval; list shows accounts & sample."""
    database = tmp_path / "events.sqlite3"
    monkeypatch.setattr(cli, "_default_database_path", lambda: database)

    assert cli.main(["simulate", "spam"]) == 0
    sim_out = capsys.readouterr().out
    assert "pending approval #1" in sim_out
    assert "accounts=6" in sim_out

    assert cli.main(["approvals", "list"]) == 0
    list_out = capsys.readouterr().out
    assert "rule=spam-detector" in list_out
    assert "accounts=6" in list_out
    assert "sample=" in list_out
    assert "https://" not in list_out


def test_cli_events_redacts_chat_urls_and_emails_by_default(
    tmp_path, monkeypatch, capsys
):
    """R10: crew events redacts URLs, emails, and long chat text unless --full is passed."""
    database = tmp_path / "events.sqlite3"
    with SQLiteEventStore(database) as store:
        store.save_event(
            "msg-redact-1",
            "notification",
            "channel.chat.message",
            {
                "event": {
                    "message": {
                        "text": "contact test@example.com or visit https://bad.example/x right now please"
                    }
                }
            },
        )
    monkeypatch.setattr(cli, "_default_database_path", lambda: database)

    assert cli.main(["events", "--limit", "1"]) == 0
    redacted_out = capsys.readouterr().out
    assert "test@example.com" not in redacted_out
    assert "https://bad.example/x" not in redacted_out
    assert "[email]" in redacted_out


def test_cli_rules_ship_validates_and_moves_draft_to_active(
    tmp_path, monkeypatch, capsys
):
    """R8: crew rules ship validates rules/draft/<name>.json and moves it to rules/active/."""
    import json

    fake_root = tmp_path / "project"
    draft_dir = fake_root / "rules" / "draft"
    draft_dir.mkdir(parents=True)
    draft_file = draft_dir / "welcome_follow.json"
    draft_file.write_text(
        json.dumps(
            {
                "id": "welcome-follow",
                "event": "channel.follow",
                "conditions": {},
                "actions": [
                    {"action": "send_chat_message", "message": "Welcome follower!"}
                ],
                "cooldown_seconds": 30,
                "mode": "dry_run",
            }
        ),
        encoding="utf-8",
    )
    fake_cli_path = fake_root / "src" / "streamcrew" / "cli.py"
    fake_cli_path.parent.mkdir(parents=True)
    monkeypatch.setattr(cli, "__file__", str(fake_cli_path))

    assert cli.main(["rules", "ship", "welcome_follow"]) == 0
    ship_out = capsys.readouterr().out
    assert "shipped rule: welcome-follow" in ship_out
    assert not draft_file.exists()
    assert (fake_root / "rules" / "active" / "welcome_follow.json").is_file()

    assert cli.main(["rules", "list"]) == 0
    assert "welcome-follow" in capsys.readouterr().out


def test_cli_approvals_list_locks_approval_and_approve_checks_count(tmp_path, monkeypatch, capsys):
    """crew approvals list marks pending approvals locked, and approve supports --count."""
    import json
    from streamcrew.storage import SQLiteEventStore

    db_path = tmp_path / "events.sqlite3"
    monkeypatch.setattr(cli, "_default_database_path", lambda: db_path)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: SimpleNamespace(
            dry_run=True,
            twitch_broadcaster_id="b1",
            twitch_client_id="cid",
            twitch_user_access_token="tok",
            action_pacing_seconds=0.0,
            group_cap=25,
            spam_timeout_seconds=600,
        ),
    )

    with SQLiteEventStore(db_path) as store:
        app_id = store.save_approval(
            "spam-detector",
            {
                "action": "ban_user",
                "targets": [{"user_id": "u1", "login": "l1"}, {"user_id": "u2", "login": "l2"}],
                "summary": {"accounts": 2, "sample": "spam text"},
            },
        )

    # 1. Run crew approvals list
    assert cli.main(["approvals", "list"]) == 0
    list_out = capsys.readouterr().out
    assert "accounts=2" in list_out

    # Verify locked flag is set in database
    with SQLiteEventStore(db_path) as store:
        row = store.get_approval(app_id)
        parsed = json.loads(row["action_json"])
        assert parsed.get("locked") is True

    # 2. Count mismatch refuses approve
    with pytest.raises(SystemExit) as exc:
        cli.main(["approve", str(app_id), "--count", "5"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "target count mismatch" in err

    # 3. Both crew approve and crew approvals approve work when count matches
    assert cli.main(["approvals", "approve", str(app_id), "--count", "2"]) == 0
    out = capsys.readouterr().out
    assert f"approval {app_id}: done" in out


def test_cli_simulate_test_alt_creates_isolated_approval(tmp_path, monkeypatch, capsys):
    """crew simulate test-alt creates a safe approval targeting only the specified user."""
    import json
    from streamcrew.storage import SQLiteEventStore

    db_path = tmp_path / "events.sqlite3"
    monkeypatch.setattr(cli, "_default_database_path", lambda: db_path)

    assert cli.main(["simulate", "test-alt", "--user-id", "88888", "--login", "my_alt_account"]) == 0
    out = capsys.readouterr().out
    assert "targeting owned alt 'my_alt_account' (88888)" in out

    with SQLiteEventStore(db_path) as store:
        approvals = store.list_approvals("pending")
        assert len(approvals) == 1
        data = json.loads(approvals[0]["action_json"])
        assert data["targets"] == [{"user_id": "88888", "login": "my_alt_account"}]
        assert data["locked"] is True


def test_cli_approve_records_decided_by_audit_trail(tmp_path, monkeypatch, capsys):
    """Audit trail: crew approve --by <name> records who approved in database and output."""
    db_path = tmp_path / "events.sqlite3"
    monkeypatch.setattr(cli, "_default_database_path", lambda: db_path)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: SimpleNamespace(
            dry_run=True,
            group_cap=25,
            action_pacing_seconds=0.0,
            spam_timeout_seconds=600,
        ),
    )

    with SQLiteEventStore(db_path) as store:
        app_id = store.save_approval(
            "spam-detector",
            {
                "action": "ban_user",
                "targets": [{"user_id": "u1", "login": "l1"}],
                "summary": {"accounts": 1, "sample": "spam"},
            },
        )

    assert cli.main(["approve", str(app_id), "--count", "1", "--by", "Sam"]) == 0
    out = capsys.readouterr().out
    assert f"approval {app_id}: done | by=Sam" in out

    with SQLiteEventStore(db_path) as store:
        row = store.get_approval(app_id)
        assert row["status"] == "done"
        assert row["decided_by"] == "Sam"

    assert cli.main(["approvals", "list", "--status", "done"]) == 0
    list_out = capsys.readouterr().out
    assert "by=Sam" in list_out
