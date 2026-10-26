"""List and decide on queued StreamCrew actions before they reach Twitch."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from .actions import execute_action, record_marker_result

logger = logging.getLogger(__name__)


class ApprovalError(RuntimeError):
    """An approval is missing or is no longer waiting for a decision."""


class ApprovalQueue:
    """Apply one-time approve or reject decisions to stored action requests."""

    def __init__(
        self,
        store: Any,
        settings: Any,
        action_executor: Callable[..., dict[str, Any]] = execute_action,
    ) -> None:
        self.store = store
        self.settings = settings
        self.action_executor = action_executor

    def list(self, status: str | None = "pending") -> list[dict[str, Any]]:
        """Return queued actions, pending by default."""
        return self.store.list_approvals(status)

    def reject(self, approval_id: int) -> dict[str, Any]:
        """Reject a pending action and record the CLI decision."""
        now = datetime.now(timezone.utc).isoformat()
        updated = self.store.update_approval_status(
            approval_id,
            "rejected",
            decided_at=now,
            decided_by="cli",
            expected_status="pending",
        )
        if not updated:
            raise ApprovalError("Approval does not exist or is no longer pending.")
        logger.info("Approval %s rejected.", approval_id)
        return {"id": approval_id, "status": "rejected", "decided_by": "cli"}

    def approve(self, approval_id: int) -> dict[str, Any]:
        """Mark pending work approved, execute it once, then record its outcome."""
        row = self.store.get_approval(approval_id)
        if row is None or row["status"] != "pending":
            raise ApprovalError("Approval does not exist or is no longer pending.")
        now = datetime.now(timezone.utc).isoformat()
        updated = self.store.update_approval_status(
            approval_id,
            "approved",
            decided_at=now,
            decided_by="cli",
            expected_status="pending",
        )
        if not updated:
            raise ApprovalError("Approval does not exist or is no longer pending.")

        action = json.loads(row["action_json"])
        action_name = action.get("action", "action")
        try:
            outcome = self.action_executor(
                action, "auto", self.settings, approval_granted=True
            )
            final_status = "done" if outcome.get("status") == "sent" else "failed"
            if action.get("action") == "create_marker":
                record_marker_result(
                    self.store, action, outcome, source=f"approval:{approval_id}"
                )
        except Exception as error:
            outcome = {"status": "error", "error": str(error)}
            final_status = "failed"

        self.store.update_approval_status(approval_id, final_status)
        logger.info("Approval %s %s: %s.", approval_id, final_status, action_name)
        return {"id": approval_id, "status": final_status, "result": outcome}
