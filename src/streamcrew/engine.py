"""Match saved events against rules and run dry-run or approval workflows."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .actions import record_marker_result
from .rules import conditions_match, render_value, validate_rule

logger = logging.getLogger(__name__)


class RuleEngine:
    """Evaluate rules with persisted cooldowns and explicit action modes."""

    def __init__(
        self,
        store: Any,
        action_executor: Callable[[dict[str, Any], str], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.action_executor = action_executor
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_run_by_rule: dict[str, datetime] = {}

    def _last_run(self, rule_id: str) -> datetime | None:
        value = self._last_run_by_rule.get(rule_id)
        if value is not None:
            return value
        stored = self.store.get_rule_cooldown(rule_id)
        if stored is None:
            return None
        value = datetime.fromisoformat(stored)
        self._last_run_by_rule[rule_id] = value
        return value

    def run_rule(
        self,
        rule: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Evaluate one rule and return a status record for each action."""
        normalized = validate_rule(rule)
        if normalized["event"] != event_type:
            return []
        if not conditions_match(normalized["conditions"], payload):
            return []

        now = self.clock()
        cooldown_seconds = normalized["cooldown_seconds"]
        previous = self._last_run(normalized["id"])
        if (
            previous is not None
            and cooldown_seconds > 0
            and now - previous < timedelta(seconds=cooldown_seconds)
        ):
            logger.info("Rule %s is in cooldown.", normalized["id"])
            return [{"status": "cooldown", "rule_id": normalized["id"]}]

        self._last_run_by_rule[normalized["id"]] = now
        self.store.set_rule_cooldown(normalized["id"], now)

        results: list[dict[str, Any]] = []
        for action in normalized["actions"]:
            rendered = render_value(action, payload)
            action_name = rendered["action"]
            if normalized["mode"] == "dry_run":
                details = {key: value for key, value in rendered.items() if key != "action"}
                message = f"would do {action_name}"
                if details:
                    message += f" with {details}"
                logger.info("%s", message)
                results.append(
                    {"status": "dry_run", "message": message, "action": rendered}
                )
            elif normalized["mode"] == "approve":
                approval_id = self.store.save_approval(normalized["id"], rendered)
                logger.info(
                    "Rule %s queued %s for approval (id %s).",
                    normalized["id"],
                    action_name,
                    approval_id,
                )
                results.append(
                    {
                        "status": "pending",
                        "approval_id": approval_id,
                        "action": rendered,
                    }
                )
            else:
                if self.action_executor is None:
                    raise RuntimeError(
                        "Auto mode requires the action layer, which is not available yet."
                    )
                outcome = self.action_executor(rendered, normalized["mode"])
                if action_name == "create_marker":
                    record_marker_result(
                        self.store, rendered, outcome, source=normalized["id"]
                    )
                results.append(
                    {"status": "auto", "action": rendered, "result": outcome}
                )
        return results
