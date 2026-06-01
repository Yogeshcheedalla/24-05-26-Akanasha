from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, utc_now


class ExplainableAIEngine:
    """Records why Akansha selected a workflow, agents, skills, and tools."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def explain_action(
        self,
        task: str,
        analysis: dict[str, Any],
        workflow: dict[str, Any],
        hiring_plan: dict[str, Any],
        skill_routes: list[str],
        tool_plan: dict[str, Any],
        confidence: float | None = None,
    ) -> dict[str, Any]:
        workflow_selection = {
            "workflow_id": workflow.get("id"),
            "intent": workflow.get("intent") or analysis.get("intent"),
            "steps": workflow.get("steps", []),
            "reason": f"Workflow matched intent '{analysis.get('intent')}' and risk '{analysis.get('risk_level')}'.",
        }
        agent_selection = {
            "persistent_core": True,
            "temporary_worker_count": hiring_plan.get("temporary_worker_count", 0),
            "agent_types": hiring_plan.get("agent_types", []),
            "reason": "Coordinator uses bounded agents and prevents worker recursion.",
        }
        skill_selection = {
            "skills": skill_routes,
            "reason": "Skills were routed from task intent and artifact/research/coding keywords.",
        }
        tool_selection = {
            "tools": tool_plan.get("selected_tools", []),
            "approval_required": tool_plan.get("approval_required", False),
            "reason": "Universal tool layer enforces risk and approval boundaries.",
        }
        explanation_confidence = confidence if confidence is not None else self._confidence(analysis, workflow, hiring_plan)
        reason = self._reason(task, analysis, workflow_selection, agent_selection, skill_selection)
        payload = {
            "analysis": analysis,
            "workflow_selection": workflow_selection,
            "agent_selection": agent_selection,
            "skill_selection": skill_selection,
            "tool_selection": tool_selection,
        }
        explanation_id = f"explain_{uuid4().hex}"
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO action_explanations(
                    id, task, reason, confidence, workflow_selection, agent_selection,
                    skill_selection, tool_selection, risk_level, payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    explanation_id,
                    task,
                    reason,
                    explanation_confidence,
                    dumps(workflow_selection),
                    dumps(agent_selection),
                    dumps(skill_selection),
                    dumps(tool_selection),
                    analysis.get("risk_level", "unknown"),
                    dumps(payload),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM action_explanations WHERE id = ?", (explanation_id,)).fetchone()
        return self._decode(row)

    def list_explanations(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM action_explanations ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _reason(
        self,
        task: str,
        analysis: dict[str, Any],
        workflow_selection: dict[str, Any],
        agent_selection: dict[str, Any],
        skill_selection: dict[str, Any],
    ) -> str:
        return (
            f"Task '{task[:120]}' was classified as {analysis.get('intent')} with "
            f"{analysis.get('risk_level')} risk. Hermes selected {workflow_selection['intent']} workflow, "
            f"{agent_selection['temporary_worker_count']} temporary workers, and "
            f"{len(skill_selection['skills'])} skills to keep execution auditable."
        )

    def _confidence(self, analysis: dict[str, Any], workflow: dict[str, Any], hiring_plan: dict[str, Any]) -> float:
        base = float(workflow.get("confidence", 0.72))
        uncertainty = float(analysis.get("uncertainty_score", 0.5))
        worker_bonus = min(0.08, hiring_plan.get("temporary_worker_count", 0) * 0.015)
        return round(max(0.45, min(0.95, base - uncertainty * 0.12 + worker_bonus)), 3)

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("workflow_selection", "agent_selection", "skill_selection", "tool_selection", "payload"):
            data[key] = loads(data.get(key), {})
        return data

