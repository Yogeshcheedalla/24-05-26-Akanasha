from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class SelfHealingEngine:
    """Builds recovery plans for blocked, failed, or low-confidence workflows."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def recover(
        self,
        task: str,
        analysis: dict[str, Any],
        validation: dict[str, Any],
        tool_plan: dict[str, Any],
        safety: dict[str, Any],
        collaboration: dict[str, Any],
    ) -> dict[str, Any]:
        root_causes = self._root_causes(analysis, validation, tool_plan, safety, collaboration)
        strategy = self._strategy(root_causes, analysis)
        status = "recovery_not_needed" if not root_causes else "recovery_plan_ready"
        confidence = round(max(0.25, 0.88 - (len(root_causes) * 0.08)), 3)
        now = utc_now()
        fingerprint = stable_fingerprint(f"{task}:{','.join(root_causes)}:{status}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM self_healing_events WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing, deduplicated=True)
            event_id = f"heal_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO self_healing_events(
                    id, task, failure_type, root_cause, recovery_plan,
                    validation, confidence, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    task,
                    root_causes[0] if root_causes else "none",
                    dumps(root_causes),
                    dumps(strategy),
                    dumps({"validation": validation, "safety": safety, "tool_plan": tool_plan}),
                    confidence,
                    status,
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM self_healing_events WHERE id = ?", (event_id,)).fetchone()
        return self._decode(row) if row else {"id": event_id, "status": status}

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM self_healing_events ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _root_causes(
        self,
        analysis: dict[str, Any],
        validation: dict[str, Any],
        tool_plan: dict[str, Any],
        safety: dict[str, Any],
        collaboration: dict[str, Any],
    ) -> list[str]:
        causes: list[str] = []
        if not validation.get("valid", True):
            causes.append("validation_failed")
        if tool_plan.get("blocked_tools"):
            causes.append("tool_permission_blocked")
        if safety.get("requires_approval"):
            causes.append("owner_approval_required")
        if collaboration.get("needs_user_input"):
            causes.append("human_input_required")
        if float(analysis.get("uncertainty_score", 0.0)) >= 0.68:
            causes.append("low_confidence_assumption")
        if analysis.get("risk_level") in {"high", "critical"}:
            causes.append("sensitive_action_guard")
        return list(dict.fromkeys(causes))

    def _strategy(self, root_causes: list[str], analysis: dict[str, Any]) -> dict[str, Any]:
        steps: list[str] = []
        alternate_tools: list[str] = []
        agent_switches: list[str] = []
        rollback = "recorded_checkpoint_only"
        if "tool_permission_blocked" in root_causes:
            steps.append("Retry using approved tools first")
            alternate_tools.extend(["Web/API Gateway", "Hermes Database", "Plugin Runtime"])
        if "owner_approval_required" in root_causes or "sensitive_action_guard" in root_causes:
            steps.append("Pause irreversible execution until explicit owner approval")
            rollback = "rollback_to_plan_only_state"
        if "human_input_required" in root_causes:
            steps.append("Ask one focused clarification question and continue after reply")
        if "validation_failed" in root_causes:
            steps.append("Rebuild workflow path and run validation agent again")
            agent_switches.extend(["QualityAgent", "TestingAgent"])
        if "low_confidence_assumption" in root_causes:
            steps.append("Cross-check memory, tools, and sources before execution")
            agent_switches.extend(["ResearchAgent", "AnalysisAgent"])
        if not steps:
            steps.append("Continue normal workflow and keep monitoring for failures")
        return {
            "retry_policy": {"max_retries": 2, "backoff_seconds": [2, 5]},
            "alternative_strategy": steps,
            "alternate_tools": list(dict.fromkeys(alternate_tools)),
            "agent_switches": list(dict.fromkeys(agent_switches)),
            "rollback": rollback,
            "continue_policy": "resume_after_validation" if root_causes else "continue",
            "intent": analysis.get("intent"),
        }

    def _decode(self, row: Any, deduplicated: bool = False) -> dict[str, Any]:
        data = dict(row)
        data["root_cause"] = loads(data.get("root_cause"), [])
        data["recovery_plan"] = loads(data.get("recovery_plan"), {})
        data["validation"] = loads(data.get("validation"), {})
        data["deduplicated"] = deduplicated
        return data
