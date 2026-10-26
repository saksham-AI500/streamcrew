"""Command-line entry point for StreamCrew's local tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .approvals import ApprovalError, ApprovalQueue
from .config import load_config
from .eventsub import EventSubClient
from .engine import RuleEngine
from .rules import RuleValidationError, load_rule
from .storage import SQLiteEventStore
from .subscriptions import SubscriptionManager


def _default_database_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    database = project_root / "data" / "events.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    return database


async def _listen() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_config()
    with SQLiteEventStore(_default_database_path()) as store:
        manager = SubscriptionManager(settings)
        client = EventSubClient(
            settings,
            store,
            subscribe_callback=manager.create_for_session,
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
    approvals_command = commands.add_parser("approvals", help="inspect queued actions")
    approval_commands = approvals_command.add_subparsers(
        dest="approvals_command", required=True
    )
    approval_list = approval_commands.add_parser("list", help="list pending approvals")
    approval_list.add_argument(
        "--status", choices=("pending", "approved", "rejected", "done", "failed")
    )
    approve_command = commands.add_parser("approve", help="approve and run a queued action")
    approve_command.add_argument("id", type=int)
    reject_command = commands.add_parser("reject", help="reject a queued action")
    reject_command.add_argument("id", type=int)
    events_command = commands.add_parser("events", help="list recent EventSub events")
    events_command.add_argument("--limit", type=int, default=50)
    test_command = commands.add_parser("test", help="run rules against a saved fixture")
    test_command.add_argument("fixture")
    commands.add_parser("serve", help="start the local API on 127.0.0.1:8765")
    args = parser.parse_args(argv)
    if args.command == "listen":
        try:
            asyncio.run(_listen())
        except KeyboardInterrupt:
            return 0
        except Exception as error:
            parser.exit(1, f"crew listen failed: {type(error).__name__}\n")
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
        files = sorted(rules_directory.glob("*.json"))
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
    elif args.command == "approvals":
        with SQLiteEventStore(_default_database_path()) as store:
            queue = ApprovalQueue(store, settings=None)
            for approval in queue.list(args.status):
                print(
                    f"{approval['id']} | {approval['status']} | "
                    f"rule={approval['rule_id']} | action={approval['action_json']}"
                )
    elif args.command in {"approve", "reject"}:
        try:
            settings = load_config() if args.command == "approve" else None
            with SQLiteEventStore(_default_database_path()) as store:
                queue = ApprovalQueue(store, settings=settings)
                result = (
                    queue.approve(args.id)
                    if args.command == "approve"
                    else queue.reject(args.id)
                )
            print(f"approval {result['id']}: {result['status']}")
        except (ApprovalError, ValueError, OSError) as error:
            parser.exit(1, f"crew {args.command} failed: {error}\n")
    elif args.command == "events":
        if args.limit < 1:
            parser.error("--limit must be a positive integer")
        with SQLiteEventStore(_default_database_path()) as store:
            print(json.dumps(store.list_events(args.limit), indent=2))
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
        rules = [load_rule(path) for path in sorted(rules_directory.glob("*.json"))]
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
