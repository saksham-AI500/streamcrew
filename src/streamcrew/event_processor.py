"""Connect deduplicated Twitch notifications to rules and highlight detection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from .actions import execute_action
from .engine import RuleEngine
from .highlights import HighlightDetector
from .spam import SpamDetector, build_spam_approval_action


class EventProcessor:
    """Evaluate stored EventSub notifications using the shared engine."""

    def __init__(
        self,
        settings: Any,
        store: Any,
        rules: list[dict[str, Any]] | None = None,
        action_executor: Callable[..., dict[str, Any]] = execute_action,
        clock: Callable[[], datetime] | None = None,
        rules_loader: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.rules = rules if rules is not None else []
        self.rules_loader = rules_loader
        self.clock = clock or (lambda: datetime.now(timezone.utc))

        def execute(action: dict[str, Any], mode: str, *_extra: Any) -> dict[str, Any]:
            return action_executor(action, mode, settings)

        self.engine = RuleEngine(store, action_executor=execute, clock=self.clock)
        self.highlights = HighlightDetector(
            settings,
            mode="auto",
            action_executor=execute,
            clock=self.clock,
            store=store,
        )
        self.spam = SpamDetector(settings, clock=self.clock)
        self._active_spam_approval_id: int | None = None

    def process_notification(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        """Run matching rules once for a newly stored notification."""
        metadata = message.get("metadata", {})
        event_type = metadata.get("subscription_type")
        event = message.get("payload", {}).get("event")
        if not isinstance(event_type, str) or not isinstance(event, dict):
            return []

        active_rules = self.rules_loader() if self.rules_loader is not None else self.rules
        results: list[dict[str, Any]] = []
        for rule in active_rules:
            results.extend(self.engine.run_rule(rule, event_type, event))

        if event_type == "channel.chat.message":
            chat_message = event.get("message")
            text = chat_message.get("text") if isinstance(chat_message, dict) else None
            if isinstance(text, str) and text.strip():
                try:
                    timestamp = datetime.fromisoformat(
                        str(metadata.get("message_timestamp", "")).replace(
                            "Z", "+00:00"
                        )
                    )
                except ValueError:
                    timestamp = self.clock()
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                incident = self.spam.observe_message(
                    message, timestamp=timestamp, include_updates=True
                )
                if incident is not None:
                    group_cap = int(getattr(self.settings, "group_cap", 25))
                    action = build_spam_approval_action(incident, group_cap=group_cap)
                    merged = False
                    if incident.get("is_update") and self._active_spam_approval_id is not None:
                        existing = self.store.get_approval(self._active_spam_approval_id)
                        if existing and existing.get("status") == "pending":
                            try:
                                parsed = json.loads(existing.get("action_json", "{}"))
                            except (ValueError, TypeError):
                                parsed = {}
                            if not parsed.get("locked"):
                                self.store.update_approval_status(
                                    self._active_spam_approval_id,
                                    "pending",
                                    expected_status="pending",
                                    action_json=action,
                                )
                                merged = True
                    if not merged:
                        approval_id = self.store.save_approval("spam-detector", action)
                        self._active_spam_approval_id = approval_id
                        results.append(
                            {
                                "status": "pending",
                                "rule_id": "spam-detector",
                                "approval_id": approval_id,
                                "action": action,
                                "incident": incident,
                            }
                        )
                else:
                    highlight = self.highlights.observe_message(timestamp)
                    if highlight is not None:
                        results.append({"status": "highlight", "result": highlight})
        return results
