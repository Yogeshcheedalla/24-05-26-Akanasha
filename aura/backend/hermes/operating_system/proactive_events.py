from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class ProactiveEventEngine:
    """Detects useful proactive signals without executing side effects."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def observe(
        self,
        task: str,
        analysis: dict[str, Any],
        execution: dict[str, Any],
        self_healing: dict[str, Any],
    ) -> dict[str, Any]:
        events = self._events(task, analysis, execution, self_healing)
        stored: list[dict[str, Any]] = []
        for event in events:
            stored.append(self._store_event(task, event))
        return {
            "events": stored,
            "count": len(stored),
            "monitoring_scope": [
                "goals",
                "deadlines",
                "projects",
                "calendar",
                "system_activity",
                "workflow_delays",
                "task_failures",
                "patterns",
            ],
        }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM proactive_events ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _events(
        self,
        task: str,
        analysis: dict[str, Any],
        execution: dict[str, Any],
        self_healing: dict[str, Any],
    ) -> list[dict[str, Any]]:
        lowered = task.lower()
        events: list[dict[str, Any]] = []
        if re.search(r"\b(deadline|tomorrow|today|exam|submission|due)\b", lowered):
            events.append(
                {
                    "event_type": "deadline_risk",
                    "signal": "date_or_due_phrase",
                    "recommendation": "Create a reminder, check progress, and surface blocked tasks before the deadline.",
                    "priority": 0.86,
                    "confidence": 0.82,
                }
            )
        if analysis.get("intent") == "coding" and re.search(r"\b(deploy|deployment|env|environment|github)\b", lowered):
            events.append(
                {
                    "event_type": "deployment_environment_risk",
                    "signal": "coding_deployment_phrase",
                    "recommendation": "Verify environment variables, build command, and health checks before deployment.",
                    "priority": 0.82,
                    "confidence": 0.8,
                }
            )
        if analysis.get("intent") == "artifact_generation":
            events.append(
                {
                    "event_type": "artifact_validation_ready",
                    "signal": "document_or_export_request",
                    "recommendation": "Run artifact-open verification and compare requested format against generated output.",
                    "priority": 0.72,
                    "confidence": 0.78,
                }
            )
        if self_healing.get("status") == "recovery_plan_ready":
            events.append(
                {
                    "event_type": "workflow_recovery_needed",
                    "signal": "self_healing_event",
                    "recommendation": "Review recovery plan before continuing the blocked workflow.",
                    "priority": 0.9,
                    "confidence": self_healing.get("confidence", 0.75),
                }
            )
        if execution.get("status") == "blocked_for_approval":
            events.append(
                {
                    "event_type": "approval_waiting",
                    "signal": "universal_execution_status",
                    "recommendation": "Ask the owner for approval before any irreversible action.",
                    "priority": 0.88,
                    "confidence": execution.get("confidence", 0.75),
                }
            )
        return events

    def _store_event(self, task: str, event: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        fingerprint = stable_fingerprint(f"{task}:{event['event_type']}:{event['signal']}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM proactive_events WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing, deduplicated=True)
            event_id = f"pevent_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO proactive_events(
                    id, event_type, source, signal, recommendation, priority,
                    confidence, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event["event_type"],
                    "akansha_operating_system",
                    event["signal"],
                    event["recommendation"],
                    event["priority"],
                    event["confidence"],
                    "open",
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM proactive_events WHERE id = ?", (event_id,)).fetchone()
        return self._decode(row) if row else {"id": event_id, **event}

    def _decode(self, row: Any, deduplicated: bool = False) -> dict[str, Any]:
        data = dict(row)
        data["deduplicated"] = deduplicated
        return data
