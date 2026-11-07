"""Command-line entry point for StreamCrew's local tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
from pathlib import Path
from types import SimpleNamespace

from .approvals import ApprovalError, ApprovalQueue
from .config import load_config
from .eventsub import EventSubClient
from .engine import RuleEngine
from .event_processor import EventProcessor
from .redact import redact_event, redact_text
from .rules import RuleValidationError, load_rule
from .storage import SQLiteEventStore
from .subscriptions import SubscriptionManager


def _default_database_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    database = project_root / "data" / "events.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    return database


def _rule_files(rules_directory: Path) -> list[Path]:
    """Return active rule files from rules/active/*.json and rules/*.json."""
    active_dir = rules_directory / "active"
    files = list(sorted(active_dir.glob("*.json"))) if active_dir.is_dir() else []
    seen = {p.name for p in files}
    for path in sorted(rules_directory.glob("*.json")):
        if path.name not in seen:
            files.append(path)
    return files


async def _listen() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_config()
    with SQLiteEventStore(_default_database_path()) as store:
        rules_directory = Path(__file__).resolve().parents[2] / "rules"
        processor = EventProcessor(
            settings,
            store,
            rules_loader=lambda: [load_rule(p) for p in _rule_files(rules_directory)],
        )
        manager = SubscriptionManager(settings)
        client = EventSubClient(
            settings,
            store,
            subscribe_callback=manager.create_for_session,
            notification_callback=processor.process_notification,
        )
        try:
            await client.run()
        finally:
            await client.close()


def main(argv: list[str] | None = None) -> int:
    """Parse a StreamCrew command and run it."""
    parser = argparse.ArgumentParser(prog="crew")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("listen", help="connect to Twitch EventSub WebSockets")
    validate_command = commands.add_parser("validate", help="validate a JSON rule")
    validate_command.add_argument("file")
    rules_command = commands.add_parser("rules", help="inspect saved rules")
    rule_commands = rules_command.add_subparsers(dest="rules_command", required=True)
    rule_commands.add_parser("list", help="list JSON rules in the rules directory")
    ship_command = rule_commands.add_parser(
        "ship", help="validate a draft rule and move it to active"
    )
    ship_command.add_argument("name")
    approvals_command = commands.add_parser("approvals", help="inspect queued actions")
    approval_commands = approvals_command.add_subparsers(
        dest="approvals_command", required=True
    )
    approval_list = approval_commands.add_parser("list", help="list pending approvals")
    approval_list.add_argument(
        "--status", choices=("pending", "approved", "rejected", "done", "failed")
    )
    app_approve = approval_commands.add_parser(
        "approve", help="approve and run a queued action"
    )
    app_approve.add_argument("id", type=int)
    app_approve.add_argument(
        "--count", "-c", type=int, default=None, help="refuse if target count differs"
    )
    app_approve.add_argument(
        "--by", "-b", default="cli", help="human moderator name who approved"
    )
    app_reject = approval_commands.add_parser(
        "reject", help="reject a queued action"
    )
    app_reject.add_argument("id", type=int)
    app_reject.add_argument(
        "--by", "-b", default="cli", help="human moderator name who rejected"
    )

    approve_command = commands.add_parser("approve", help="approve and run a queued action")
    approve_command.add_argument("id", type=int)
    approve_command.add_argument(
        "--count", "-c", type=int, default=None, help="refuse if target count differs"
    )
    approve_command.add_argument(
        "--by", "-b", default="cli", help="human moderator name who approved"
    )
    reject_command = commands.add_parser("reject", help="reject a queued action")
    reject_command.add_argument("id", type=int)
    reject_command.add_argument(
        "--by", "-b", default="cli", help="human moderator name who rejected"
    )
    events_command = commands.add_parser("events", help="list recent EventSub events")
    events_command.add_argument("--limit", type=int, default=50)
    events_command.add_argument(
        "--metadata-only",
        action="store_true",
        help="omit decoded payloads from the output",
    )
    events_command.add_argument(
        "--full",
        action="store_true",
        help="print unredacted payloads (humans only)",
    )
    test_command = commands.add_parser("test", help="run rules against a saved fixture")
    test_command.add_argument("fixture")
    test_command.add_argument("--rule", default=None, help="optional rule file to test")
    simulate_command = commands.add_parser(
        "simulate", help="feed a fixture burst through detector and queue"
    )
    simulate_command.add_argument("scenario", choices=("spam", "test-alt"))
    simulate_command.add_argument("--fixture", default=None)
    simulate_command.add_argument("--user-id", default=None, help="alt account user ID")
    simulate_command.add_argument("--login", default=None, help="alt account login name")
    commands.add_parser("serve", help="start the local API on 127.0.0.1:8765")
    args = parser.parse_args(argv)
    if args.command == "listen":
        try:
            asyncio.run(_listen())
        except KeyboardInterrupt:
            return 0
        except Exception as error:
            # Configuration and filesystem errors have safe, useful messages.
            # Other exception text is omitted in case it contains credentials.
            detail = (
                str(error)
                if isinstance(error, (ValueError, OSError))
                else type(error).__name__
            )
            parser.exit(1, f"crew listen failed: {detail}\n")
    elif args.command == "validate":
        try:
            rule = load_rule(args.file)
        except RuleValidationError as error:
            parser.exit(1, f"invalid rule: {error}\n")
        print(
            f"valid rule: {rule['id']} | event={rule['event']} | mode={rule['mode']}"
        )
    elif args.command == "rules" and args.rules_command == "list":
        rules_directory = Path(__file__).resolve().parents[2] / "rules"
        files = _rule_files(rules_directory)
        if not files:
            print("No rule files found.")
        for path in files:
            try:
                rule = load_rule(path)
            except RuleValidationError as error:
                print(f"invalid rule: {path.name}: {error}")
                continue
            print(
                f"{rule['id']} | event={rule['event']} | mode={rule['mode']}"
            )
    elif args.command == "rules" and args.rules_command == "ship":
        rules_directory = Path(__file__).resolve().parents[2] / "rules"
        stem = args.name if args.name.endswith(".json") else f"{args.name}.json"
        draft_path = rules_directory / "draft" / Path(stem).name
        if not draft_path.is_file():
            parser.exit(1, f"draft rule not found: {draft_path}\n")
        try:
            rule = load_rule(draft_path)
        except RuleValidationError as error:
            parser.exit(1, f"invalid rule: {error}\n")
        active_dir = rules_directory / "active"
        active_dir.mkdir(parents=True, exist_ok=True)
        dest_path = active_dir / draft_path.name
        shutil.move(str(draft_path), str(dest_path))
        print(f"shipped rule: {rule['id']} -> {dest_path}")
    elif args.command == "approvals":
        if args.approvals_command == "list":
            with SQLiteEventStore(_default_database_path()) as store:
                queue = ApprovalQueue(store, settings=None)
                for approval in queue.list(args.status):
                    extra = ""
                    try:
                        parsed = json.loads(approval["action_json"])
                        if isinstance(parsed, dict) and (
                            "summary" in parsed or "targets" in parsed
                        ):
                            summary = parsed.get("summary") or {}
                            targets = parsed.get("targets") or []
                            accounts = summary.get("accounts", len(targets))
                            sample = redact_text(str(summary.get("sample", "")))
                            extra = f" | accounts={accounts} | sample={sample!r}"
                        # Lock pending approval when shown to human or agent to prevent silent expansion
                        if (
                            isinstance(parsed, dict)
                            and approval["status"] == "pending"
                            and not parsed.get("locked")
                        ):
                            locked_action = {**parsed, "locked": True}
                            store.update_approval_status(
                                approval["id"],
                                "pending",
                                expected_status="pending",
                                action_json=locked_action,
                            )
                    except (ValueError, TypeError):
                        pass
                    decided_by_info = (
                        f" | by={approval['decided_by']}"
                        if approval.get("decided_by")
                        else ""
                    )
                    print(
                        f"{approval['id']} | {approval['status']}{decided_by_info} | "
                        f"rule={approval['rule_id']}{extra} | action={approval['action_json']}"
                    )
        elif args.approvals_command in {"approve", "reject"}:
            try:
                settings = load_config() if args.approvals_command == "approve" else None
                with SQLiteEventStore(_default_database_path()) as store:
                    queue = ApprovalQueue(store, settings=settings)
                    result = (
                        queue.approve(
                            args.id,
                            expected_count=getattr(args, "count", None),
                            decided_by=getattr(args, "by", "cli"),
                        )
                        if args.approvals_command == "approve"
                        else queue.reject(args.id, decided_by=getattr(args, "by", "cli"))
                    )
                print(
                    f"approval {result['id']}: {result['status']} | by={result.get('decided_by', 'cli')}"
                )
            except (ApprovalError, ValueError, OSError) as error:
                parser.exit(1, f"crew approvals {args.approvals_command} failed: {error}\n")
    elif args.command in {"approve", "reject"}:
        try:
            settings = load_config() if args.command == "approve" else None
            with SQLiteEventStore(_default_database_path()) as store:
                queue = ApprovalQueue(store, settings=settings)
                result = (
                    queue.approve(
                        args.id,
                        expected_count=getattr(args, "count", None),
                        decided_by=getattr(args, "by", "cli"),
                    )
                    if args.command == "approve"
                    else queue.reject(args.id, decided_by=getattr(args, "by", "cli"))
                )
            print(
                f"approval {result['id']}: {result['status']} | by={result.get('decided_by', 'cli')}"
            )
        except (ApprovalError, ValueError, OSError) as error:
            parser.exit(1, f"crew {args.command} failed: {error}\n")
    elif args.command == "events":
        if args.limit < 1:
            parser.error("--limit must be a positive integer")
        with SQLiteEventStore(_default_database_path()) as store:
            events = store.list_events(args.limit)
            if args.metadata_only:
                events = [
                    {key: value for key, value in event.items() if key != "payload"}
                    for event in events
                ]
            elif not args.full:
                events = [redact_event(event) for event in events]
            print(json.dumps(events, indent=2))
    elif args.command == "test":
        fixture_path = Path(args.fixture)
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            parser.exit(1, f"could not read fixture: {error}\n")
        metadata = fixture.get("metadata", {})
        event_type = metadata.get("subscription_type") or fixture.get("event_type")
        payload = fixture.get("payload", {}).get("event", fixture.get("payload", fixture))
        if not event_type or not isinstance(payload, dict):
            parser.error("fixture must contain metadata.subscription_type and an event object")
        rules_directory = Path(__file__).resolve().parents[2] / "rules"
        if args.rule:
            rules = [load_rule(args.rule)]
        else:
            rules = [load_rule(path) for path in _rule_files(rules_directory)]
        matched = False
        with SQLiteEventStore(":memory:") as store:
            engine = RuleEngine(store)
            for rule in rules:
                safe_rule = {**rule, "mode": "dry_run"}
                results = engine.run_rule(safe_rule, event_type, payload)
                for result in results:
                    matched = True
                    print(result.get("message", f"would do {result['action']['action']}"))
        if not matched:
            print("No rule matched this fixture.")
    elif args.command == "simulate":
        if args.scenario == "test-alt":
            if not args.user_id or not args.login:
                parser.error("simulate test-alt requires both --user-id and --login")
            alt_action = {
                "action": "ban_user",
                "duration": 30,
                "reason": "manual live test on owned alt account",
                "targets": [{"user_id": str(args.user_id), "login": str(args.login)}],
                "results": [],
                "summary": {"accounts": 1, "sample": "manual live test target"},
                "locked": True,
            }
            with SQLiteEventStore(_default_database_path()) as store:
                app_id = store.save_approval("live-test", alt_action)
                print(
                    f"Created safe live-test approval #{app_id} targeting owned alt '{args.login}' ({args.user_id}).\n"
                    f"Verify with:  crew approvals list\n"
                    f"Approve with: crew approve {app_id}"
                )
            return 0
        project_root = Path(__file__).resolve().parents[2]
        fixture_path = (
            Path(args.fixture)
            if args.fixture
            else project_root / "fixtures" / "spam_burst.json"
        )
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            parser.exit(1, f"could not read fixture: {error}\n")
        messages = fixture.get("messages", []) if isinstance(fixture, dict) else fixture
        if not isinstance(messages, list) or not messages:
            parser.exit(1, "fixture must contain a non-empty messages list\n")
        sim_settings = SimpleNamespace(
            dry_run=True,
            spam_min_accounts=5,
            spam_window_seconds=10,
            spam_cooldown_seconds=60,
            spam_timeout_seconds=600,
            group_cap=25,
            action_pacing_seconds=0.5,
        )

        def _no_network(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {"status": "dry_run"}

        created: list[dict[str, object]] = []
        with SQLiteEventStore(_default_database_path()) as store:
            processor = EventProcessor(
                sim_settings, store, rules=[], action_executor=_no_network
            )
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                meta = msg.get("metadata", {})
                msg_id = str(meta.get("message_id") or "")
                if msg_id:
                    store.save_event(
                        msg_id,
                        str(meta.get("message_type") or "notification"),
                        meta.get("subscription_type"),
                        msg.get("payload", msg),
                    )
                for outcome in processor.process_notification(msg):
                    if outcome.get("status") == "pending":
                        created.append(outcome)
            for item in created:
                row = store.get_approval(int(item["approval_id"]))
                parsed = json.loads(row["action_json"]) if row else {}
                summary = parsed.get("summary") or {}
                accounts = summary.get("accounts", 0)
                sample = redact_text(str(summary.get("sample", "")))
                print(
                    f"pending approval #{item['approval_id']}: "
                    f"rule={item.get('rule_id', 'spam-detector')} | "
                    f"accounts={accounts} | sample={sample!r}"
                )
        if not created:
            print("No incident triggered from fixture.")
    elif args.command == "serve":
        try:
            import uvicorn

            from .api import create_app

            uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="info")
        except Exception as error:
            parser.exit(1, f"crew serve failed: {type(error).__name__}: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
