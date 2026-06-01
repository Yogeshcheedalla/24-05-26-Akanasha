from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from .common import clamp, compact_keywords


class LifeAutomationEngine:
    """Creates governed plans for reminders, bills, follow-ups, and deadlines."""

    AUTOMATION_TYPES = {
        "reminder": ["remind", "reminder", "alert", "alarm"],
        "subscription": ["subscription", "renewal", "plan"],
        "bill": ["bill", "payment due", "invoice due"],
        "deadline": ["deadline", "due date", "submission"],
        "email_summary": ["email summary", "summarize emails"],
        "follow_up": ["follow up", "follow-up", "callback"],
        "task_schedule": ["schedule task", "todo", "to-do"],
    }

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def plan(self, user_intent: str, signals: list[str | dict[str, Any]] | None = None, approved: bool = False) -> dict[str, Any]:
        plan_id = f"life_{uuid4().hex}"
        automation_type = self._detect_type(user_intent)
        trigger = self._trigger(user_intent, signals or [])
        action_plan = self._action_plan(user_intent, automation_type, trigger)
        schedule = self._schedule(user_intent, signals or [])
        confidence = self._confidence(user_intent, trigger, schedule)
        status = "scheduled_pending_execution" if approved else "waiting_for_owner_approval"
        result = {
            "id": plan_id,
            "type": "life_automation",
            "automation_type": automation_type,
            "trigger": trigger,
            "action_plan": action_plan,
            "approval_state": "approved" if approved else "requires_owner_approval",
            "schedule": schedule,
            "confidence": confidence,
            "status": status,
            "created_at": utc_now(),
        }
        self._store(result)
        return result

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM life_automation_plans ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _detect_type(self, text: str) -> str:
        lowered = text.lower()
        for kind, needles in self.AUTOMATION_TYPES.items():
            if any(needle in lowered for needle in needles):
                return kind
        return "task_schedule"

    def _trigger(self, text: str, signals: list[str | dict[str, Any]]) -> dict[str, Any]:
        time_signals = re.findall(r"\b(?:today|tomorrow|\d{1,2}[:.]\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))\b", text.lower())
        return {
            "keywords": compact_keywords(text, limit=8),
            "time_signals": time_signals,
            "external_signals": signals,
            "monitoring_needed": any(word in text.lower() for word in ["monitor", "watch", "keep checking"]),
        }

    def _action_plan(self, text: str, automation_type: str, trigger: dict[str, Any]) -> list[dict[str, Any]]:
        steps = [
            {"step": "extract_intent", "detail": f"Detected {automation_type} automation"},
            {"step": "verify_schedule", "detail": "Normalize time and check conflicts before activation"},
            {"step": "ask_approval", "detail": "Owner must approve autonomous scheduling or external side effects"},
            {"step": "execute_or_monitor", "detail": "Create reminder/job only after approval"},
            {"step": "learn_pattern", "detail": "Record successful timing and wording for future title extraction"},
        ]
        if trigger["monitoring_needed"]:
            steps.insert(3, {"step": "create_monitor", "detail": "Attach bounded background monitor with max runs"})
        return steps

    def _schedule(self, text: str, signals: list[str | dict[str, Any]]) -> dict[str, Any]:
        return {
            "raw_text": text,
            "time_zone": "Asia/Calcutta",
            "signals": signals,
            "normalization_policy": "preserve_user_words_then_confirm_exact_wall_clock_time",
        }

    def _confidence(self, text: str, trigger: dict[str, Any], schedule: dict[str, Any]) -> float:
        signal_score = 0.12 if trigger["time_signals"] else 0.0
        keyword_score = min(0.18, len(trigger["keywords"]) * 0.025)
        return round(clamp(0.58 + signal_score + keyword_score), 3)

    def _store(self, result: dict[str, Any]) -> None:
        fingerprint = stable_fingerprint(f"life:{result['automation_type']}:{result['schedule']['raw_text']}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO life_automation_plans(
                    id, automation_type, trigger, action_plan, approval_state,
                    schedule, confidence, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["id"],
                    result["automation_type"],
                    dumps(result["trigger"]),
                    dumps(result["action_plan"]),
                    result["approval_state"],
                    dumps(result["schedule"]),
                    result["confidence"],
                    result["status"],
                    fingerprint,
                    result["created_at"],
                    now,
                ),
            )

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("trigger", "action_plan", "schedule"):
            data[key] = loads(data.get(key), [] if key == "action_plan" else {})
        return data
