"""SQLite-backed EventSub event storage with message-ID deduplication."""

from __future__ import annotations

import json
import sqlite3
import threading
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _serialized(method):
    """Run a store operation under its connection lock."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


class SQLiteEventStore:
    """Store received events in SQLite, keyed by their unique message ID."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database_path, check_same_thread=False
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                message_id TEXT PRIMARY KEY,
                message_type TEXT NOT NULL,
                subscription_type TEXT,
                received_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(events)")
        }
        if "message_type" not in columns and "type" in columns:
            self._connection.executescript(
                """
                ALTER TABLE events RENAME TO events_legacy;
                CREATE TABLE events (
                    message_id TEXT PRIMARY KEY,
                    message_type TEXT NOT NULL,
                    subscription_type TEXT,
                    received_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                INSERT INTO events (
                    message_id, message_type, subscription_type, received_at, payload_json
                )
                SELECT message_id, type, NULL, received_at, payload_json FROM events_legacy;
                DROP TABLE events_legacy;
                """
            )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY,
                rule_id TEXT NOT NULL,
                action_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('pending', 'approved', 'rejected', 'done', 'failed')
                ),
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_cooldowns (
                rule_id TEXT PRIMARY KEY,
                last_run_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    @_serialized
    def save_event(
        self,
        message_id: str,
        message_type: str,
        subscription_type: str | None,
        payload: Any,
    ) -> bool:
        """Save an event; return false when its message ID was already stored."""
        cursor = self._connection.execute(
            """
            INSERT OR IGNORE INTO events (
                message_id, message_type, subscription_type, received_at, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                message_id,
                message_type,
                subscription_type,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(payload, separators=(",", ":")),
            ),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    @_serialized
    def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the newest saved events with decoded payloads."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        rows = self._connection.execute(
            """
            SELECT message_id, message_type, subscription_type, received_at, payload_json
            FROM events ORDER BY rowid DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "message_id": row[0],
                "message_type": row[1],
                "subscription_type": row[2],
                "received_at": row[3],
                "payload": json.loads(row[4]),
            }
            for row in rows
        ]

    @_serialized
    def save_approval(self, rule_id: str, action: Any) -> int:
        """Add an action approval request and return its row ID."""
        cursor = self._connection.execute(
            """
            INSERT INTO approvals (rule_id, action_json, status, created_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (
                rule_id,
                json.dumps(action, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._connection.commit()
        return int(cursor.lastrowid)

    @_serialized
    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return approval rows, optionally filtered by status."""
        if status is None:
            rows = self._connection.execute(
                "SELECT * FROM approvals ORDER BY id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        names = [item[0] for item in self._connection.execute("SELECT * FROM approvals LIMIT 0").description]
        return [dict(zip(names, row, strict=True)) for row in rows]

    @_serialized
    def get_approval(self, approval_id: int) -> dict[str, Any] | None:
        """Return one approval row by ID, or None when it does not exist."""
        cursor = self._connection.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        )
        row = cursor.fetchone()
        return dict(zip((column[0] for column in cursor.description), row, strict=True)) if row else None

    @_serialized
    def update_approval_status(
        self,
        approval_id: int,
        status: str,
        *,
        decided_at: str | None = None,
        decided_by: str | None = None,
        expected_status: str | None = None,
    ) -> bool:
        """Update an approval, optionally only while it has an expected status."""
        if status not in {"pending", "approved", "rejected", "done", "failed"}:
            raise ValueError("Unsupported approval status.")
        if decided_at is None and decided_by is None:
            query = "UPDATE approvals SET status = ? WHERE id = ?"
            values: tuple[Any, ...] = (status, approval_id)
        else:
            query = (
                "UPDATE approvals SET status = ?, decided_at = ?, decided_by = ? "
                "WHERE id = ?"
            )
            values = (status, decided_at, decided_by, approval_id)
        if expected_status is not None:
            query += " AND status = ?"
            values += (expected_status,)
        cursor = self._connection.execute(query, values)
        self._connection.commit()
        return cursor.rowcount == 1

    @_serialized
    def get_rule_cooldown(self, rule_id: str) -> str | None:
        """Return the last-run timestamp for a rule, if one is stored."""
        row = self._connection.execute(
            "SELECT last_run_at FROM rule_cooldowns WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        return str(row[0]) if row else None

    @_serialized
    def set_rule_cooldown(self, rule_id: str, last_run_at: datetime) -> None:
        """Persist the last-run timestamp for a rule ID."""
        self._connection.execute(
            """
            INSERT INTO rule_cooldowns (rule_id, last_run_at) VALUES (?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET last_run_at = excluded.last_run_at
            """,
            (rule_id, last_run_at.astimezone(timezone.utc).isoformat()),
        )
        self._connection.commit()

    @_serialized
    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._connection.close()

    def __enter__(self) -> SQLiteEventStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
