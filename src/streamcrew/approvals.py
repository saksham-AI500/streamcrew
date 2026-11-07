"""List and decide on queued StreamCrew actions before they reach Twitch."""

from __future__ import annotations

import json
import logging
import time
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
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.store = store
        self.settings = settings
        self.action_executor = action_executor
        self.sleep = sleep

    def list(self, status: str | None = "pending") -> list[dict[str, Any]]:
        """Return queued actions, pending by default."""
        return self.store.list_approvals(status)

    def reject(self, approval_id: int, decided_by: str | None = None) -> dict[str, Any]:
        """Reject a pending action and record the CLI decision."""
        actor = (decided_by or "").strip() or "cli"
        now = datetime.now(timezone.utc).isoformat()
        updated = self.store.update_approval_status(
            approval_id,
            "rejected",
            decided_at=now,
            decided_by=actor,
            expected_status="pending",
        )
        if not updated:
            raise ApprovalError("Approval does not exist or is no longer pending.")
        logger.info("Approval %s rejected by %s.", approval_id, actor)
        return {"id": approval_id, "status": "rejected", "decided_by": actor}

    def _execute_grouped_ban(self, action: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """Execute a grouped ban_user action sequentially with pacing per target."""
        group_cap = int(getattr(self.settings, "group_cap", 25))
        pacing = float(getattr(self.settings, "action_pacing_seconds", 0.5))
        default_duration = int(getattr(self.settings, "spam_timeout_seconds", 600))
        duration = action.get("duration") or action.get("duration_seconds") or default_duration
        reason = action.get("reason") or "spam burst"

        raw_targets = action.get("targets") if isinstance(action.get("targets"), list) else []
        unique_targets: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for target in raw_targets:
            if not isinstance(target, dict):
                continue
            uid = str(target.get("user_id", "")).strip()
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                unique_targets.append(target)
                if len(unique_targets) >= group_cap:
                    break

        results: list[dict[str, Any]] = []
        for idx, target in enumerate(unique_targets):
            if idx > 0 and pacing > 0:
                self.sleep(pacing)
            user_id = str(target["user_id"]).strip()
            single_action: dict[str, Any] = {
                "action": "ban_user",
                "user_id": user_id,
                "duration": int(duration),
                "reason": str(reason),
            }
            try:
                outcome = self.action_executor(
                    single_action, "approve", self.settings, approval_granted=True
                )
                ok = outcome.get("status") in {"sent", "dry_run"}
                err = None if ok else str(outcome.get("error") or outcome.get("status") or "failed")
                results.append({"user_id": user_id, "ok": ok, "error": err})
            except Exception as error:
                results.append({"user_id": user_id, "ok": False, "error": str(error)})

        updated_action = dict(action)
        updated_action["results"] = results
        succeeded = sum(1 for item in results if item["ok"])
        failed = len(results) - succeeded
        final_status = "done" if (results and failed == 0) else "failed"
        summary_outcome = {
            "status": "sent" if (results and failed == 0) else ("partial" if succeeded > 0 else "failed"),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }
        return final_status, summary_outcome, updated_action

    def approve(
        self,
        approval_id: int,
        expected_count: int | None = None,
        decided_by: str | None = None,
    ) -> dict[str, Any]:
        """Mark pending work approved inside one transaction, execute it, and record results."""
        actor = (decided_by or "").strip() or "cli"
        now = datetime.now(timezone.utc).isoformat()
        claim = getattr(self.store, "claim_pending_approval", None)
        try:
            if callable(claim):
                row = claim(
                    approval_id,
                    decided_at=now,
                    decided_by=actor,
                    expected_count=expected_count,
                )
                if row is None:
                    raise ApprovalError("Approval does not exist or is no longer pending.")
            else:
                row = self.store.get_approval(approval_id)
                if row is None or row["status"] != "pending":
                    raise ApprovalError("Approval does not exist or is no longer pending.")
                if expected_count is not None:
                    try:
                        act = json.loads(row["action_json"])
                        tg = act.get("targets")
                        cnt = len(tg) if isinstance(tg, list) else act.get("summary", {}).get("accounts", 1)
                    except Exception:
                        cnt = 1
                    if cnt != expected_count:
                        raise ApprovalError(
                            f"target count mismatch: approval {approval_id} has {cnt} targets, expected {expected_count}"
                        )
                updated = self.store.update_approval_status(
                    approval_id,
                    "approved",
                    decided_at=now,
                    decided_by=actor,
                    expected_status="pending",
                )
                if not updated:
                    raise ApprovalError("Approval does not exist or is no longer pending.")
        except ValueError as err:
            raise ApprovalError(str(err)) from err

        action = json.loads(row["action_json"])
        action_name = action.get("action", "action")

        if action_name == "ban_user" and isinstance(action.get("targets"), list):
            final_status, outcome, updated_action = self._execute_grouped_ban(action)
            self.store.update_approval_status(
                approval_id, final_status, action_json=updated_action
            )
            logger.info("Approval %s %s by %s: %s (%d targets).", approval_id, final_status, actor, action_name, len(updated_action.get("targets", [])))
            return {"id": approval_id, "status": final_status, "decided_by": actor, "result": outcome}

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
        logger.info("Approval %s %s by %s: %s.", approval_id, final_status, actor, action_name)
        return {"id": approval_id, "status": final_status, "decided_by": actor, "result": outcome}
