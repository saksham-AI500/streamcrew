"""Serve StreamCrew's local event and approval views on loopback only."""

from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from .actions import execute_action
from .approvals import ApprovalError, ApprovalQueue
from .config import load_config
from .storage import SQLiteEventStore


def _database_path() -> Path:
    """Return and prepare the project's local SQLite database path."""
    project_root = Path(__file__).resolve().parents[2]
    path = project_root / "data" / "events.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def create_app(
    store: Any | None = None,
    settings: Any | None = None,
    action_executor: Any = execute_action,
) -> FastAPI:
    """Create the API app with injectable storage and settings for tests."""
    settings = settings or load_config()
    if not settings.local_api_token:
        raise ValueError("LOCAL_API_TOKEN is required to start the local API.")
    store = store or SQLiteEventStore(_database_path())
    queue = ApprovalQueue(store, settings, action_executor=action_executor)
    app = FastAPI(title="StreamCrew Local API", docs_url=None, redoc_url=None)

    def require_local_token(x_local_token: str | None) -> None:
        """Compare the submitted local API credential without timing leaks."""
        if x_local_token is None or not secrets.compare_digest(
            x_local_token, settings.local_api_token
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")

    def read_events(limit: int) -> list[dict[str, Any]]:
        """Read events, reporting a storage outage as 503 rather than 500."""
        try:
            return store.list_events(limit)
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="Storage unavailable") from error

    def list_approvals(status: str | None) -> list[dict[str, Any]]:
        """Read approvals, reporting a storage outage as 503 rather than 500."""
        try:
            return queue.list(status)
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="Storage unavailable") from error

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report that the local API and its SQLite connection are responsive."""
        try:
            store._connection.execute("SELECT 1").fetchone()
        except Exception as error:
            raise HTTPException(status_code=503, detail="Storage unavailable") from error
        return {"status": "ok", "service": "streamcrew"}

    @app.get("/events")
    def get_events(
        limit: int = Query(default=50, ge=1, le=500),
        x_local_token: str | None = Header(default=None, alias="X-Local-Token"),
    ) -> dict[str, Any]:
        """Return full recent event rows to authenticated local clients."""
        require_local_token(x_local_token)
        return {"events": read_events(limit)}

    @app.get("/overlay/events")
    def get_overlay_events(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        """Return event summaries only; chat payloads stay private."""
        return {
            "events": [
                {
                    "message_id": event["message_id"],
                    "message_type": event["message_type"],
                    "subscription_type": event["subscription_type"],
                    "received_at": event["received_at"],
                }
                for event in read_events(limit)
            ]
        }

    @app.get("/approvals")
    def get_approvals(
        status: str = Query(default="pending"),
        x_local_token: str | None = Header(default=None, alias="X-Local-Token"),
    ) -> dict[str, Any]:
        """Return full approval rows to authenticated local clients."""
        require_local_token(x_local_token)
        if status not in {"pending", "approved", "rejected", "done", "failed"}:
            raise HTTPException(status_code=422, detail="Unsupported approval status")
        return {"approvals": list_approvals(status)}

    @app.get("/overlay/approvals")
    def get_overlay_approvals() -> dict[str, Any]:
        """Return only safe approval identifiers and queue metadata."""
        summaries: list[dict[str, Any]] = []
        for approval in list_approvals("pending"):
            action_name = "action"
            accounts: int | None = None
            try:
                parsed = json.loads(approval.get("action_json", "{}"))
                if isinstance(parsed, dict):
                    action_name = str(parsed.get("action") or "action")
                    if isinstance(parsed.get("summary"), dict):
                        accounts = int(parsed["summary"].get("accounts", 0)) or None
                    elif isinstance(parsed.get("targets"), list):
                        accounts = len(parsed["targets"])
            except (ValueError, TypeError):
                pass
            item: dict[str, Any] = {
                "id": approval["id"],
                "rule_id": approval["rule_id"],
                "action": action_name,
                "status": approval["status"],
                "created_at": approval["created_at"],
            }
            if accounts is not None:
                item["accounts"] = accounts
            summaries.append(item)
        return {"approvals": summaries}

    @app.post("/approvals/{approval_id}/approve")
    def approve(
        approval_id: int,
        x_local_token: str | None = Header(default=None, alias="X-Local-Token"),
    ) -> dict[str, Any]:
        """Approve one pending action after checking the local token."""
        require_local_token(x_local_token)
        try:
            return queue.approve(approval_id)
        except ApprovalError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="Storage unavailable") from error

    @app.post("/approvals/{approval_id}/reject")
    def reject(
        approval_id: int,
        x_local_token: str | None = Header(default=None, alias="X-Local-Token"),
    ) -> dict[str, Any]:
        """Reject one pending action after checking the local token."""
        require_local_token(x_local_token)
        try:
            return queue.reject(approval_id)
        except ApprovalError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="Storage unavailable") from error

    @app.get("/overlay", response_class=HTMLResponse)
    def get_overlay() -> HTMLResponse:
        """Serve a temporary page until the standalone Phase 9 overlay is added."""
        overlay = Path(__file__).resolve().parent / "static" / "overlay.html"
        if overlay.exists():
            return HTMLResponse(overlay.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<!doctype html><title>StreamCrew</title><p>Overlay page is coming next.</p>"
        )

    return app
