"""Serve StreamCrew's local event and approval views on loopback only."""

from __future__ import annotations

import secrets
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

    @app.get("/events")
    def get_events(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        """Return recent event-log rows."""
        return {"events": store.list_events(limit)}

    @app.get("/approvals")
    def get_approvals(
        status: str = Query(default="pending"),
    ) -> dict[str, Any]:
        """Return approval rows, pending by default."""
        if status not in {"pending", "approved", "rejected", "done", "failed"}:
            raise HTTPException(status_code=422, detail="Unsupported approval status")
        return {"approvals": queue.list(status)}

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
