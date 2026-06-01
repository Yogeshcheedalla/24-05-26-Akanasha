from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from .common import task_domain


class UniversalAutonomousExecutionEngine:
    """Creates one governed execution record for every Akansha task category.

    The engine is intentionally a planner/control-plane component. It records
    the execution tree and governance state, then lets the existing coordinator,
    workflow, tool, skill, safety, and learning layers perform their normal
    responsibilities.
    """

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def create_execution(
        self,
        task: str,
        analysis: dict[str, Any],
        workflow: dict[str, Any],
        hiring_plan: dict[str, Any],
        skill_routes: list[str],
        tool_plan: dict[str, Any],
        safety: dict[str, Any],
        approved: bool,
        collaboration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        collaboration = collaboration or {}
        domain = task_domain(analysis["intent"])
        execution_tree = self._execution_tree(
            task=task,
            analysis=analysis,
            workflow=workflow,
            hiring_plan=hiring_plan,
            skill_routes=skill_routes,
            tool_plan=tool_plan,
            safety=safety,
        )
        verification = self._verification(analysis, tool_plan, safety)
        learning_update = self._learning_update(analysis, verification)
        dashboard_update = {
            "panels": [
                "current_goal",
                "current_workflow",
                "execution_tree",
                "active_agents",
                "skills_used",
                "learning_updates",
                "failures",
                "recovery_actions",
                "system_health",
                "prediction_confidence",
                "latency",
                "suggestions",
                "blocked_tasks",
            ],
            "status": "updated",
        }
        status = (
            "waiting_for_user_input"
            if collaboration.get("needs_user_input")
            else "blocked_for_approval"
            if safety.get("requires_approval") and not approved
            else "ready"
        )
        confidence = round(
            max(
                0.25,
                min(
                    0.94,
                    1.0
                    - (float(analysis.get("uncertainty_score", 0.5)) * 0.35)
                    - (0.15 if safety.get("requires_approval") and not approved else 0.0)
                    - (0.1 if tool_plan.get("blocked_tools") else 0.0),
                ),
            ),
            3,
        )
        now = utc_now()
        fingerprint = stable_fingerprint(f"{task}:{analysis['intent']}:{workflow.get('id')}:{status}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM universal_executions WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing, deduplicated=True)
            execution_id = f"uexec_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO universal_executions(
                    id, task, domain, intent, execution_tree, verification,
                    learning_update, dashboard_update, confidence, status,
                    approved, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    task,
                    domain,
                    analysis["intent"],
                    dumps(execution_tree),
                    dumps(verification),
                    dumps(learning_update),
                    dumps(dashboard_update),
                    confidence,
                    status,
                    int(approved),
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM universal_executions WHERE id = ?", (execution_id,)).fetchone()
        return self._decode(row) if row else {"id": execution_id, "status": status}

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM universal_executions ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _execution_tree(
        self,
        task: str,
        analysis: dict[str, Any],
        workflow: dict[str, Any],
        hiring_plan: dict[str, Any],
        skill_routes: list[str],
        tool_plan: dict[str, Any],
        safety: dict[str, Any],
    ) -> dict[str, Any]:
        nodes = [
            {"id": "user_goal", "type": "input", "label": task},
            {"id": "intent_detection", "type": "analysis", "label": analysis["intent"]},
            {"id": "task_classification", "type": "domain", "label": task_domain(analysis["intent"])},
            {"id": "task_decomposition", "type": "steps", "count": len(analysis.get("steps", []))},
            {"id": "complexity_analysis", "type": "score", "value": analysis.get("complexity_score")},
            {"id": "coordinator", "type": "agent", "label": "CoordinatorAgent"},
            {"id": "skill_selection", "type": "skills", "skills": skill_routes},
            {"id": "agent_assignment", "type": "agents", "agents": hiring_plan.get("agent_types", [])},
            {"id": "workflow_generation", "type": "workflow", "workflow_id": workflow.get("id")},
            {"id": "execution", "type": "tool_plan", "selected_tools": tool_plan.get("selected_tools", [])},
            {"id": "verification", "type": "safety", "requires_approval": safety.get("requires_approval")},
            {"id": "learning_update", "type": "learning", "label": "record outcome and lessons"},
            {"id": "dashboard_update", "type": "observability", "label": "refresh cognitive dashboard"},
        ]
        edges = [
            {"source": "user_goal", "target": "intent_detection"},
            {"source": "intent_detection", "target": "task_classification"},
            {"source": "task_classification", "target": "task_decomposition"},
            {"source": "task_decomposition", "target": "complexity_analysis"},
            {"source": "complexity_analysis", "target": "coordinator"},
            {"source": "coordinator", "target": "skill_selection"},
            {"source": "skill_selection", "target": "agent_assignment"},
            {"source": "agent_assignment", "target": "workflow_generation"},
            {"source": "workflow_generation", "target": "execution"},
            {"source": "execution", "target": "verification"},
            {"source": "verification", "target": "learning_update"},
            {"source": "learning_update", "target": "dashboard_update"},
        ]
        return {"nodes": nodes, "edges": edges}

    def _verification(
        self,
        analysis: dict[str, Any],
        tool_plan: dict[str, Any],
        safety: dict[str, Any],
    ) -> dict[str, Any]:
        checks = [
            "intent_verified",
            "task_decomposition_created",
            "workflow_generated",
            "agent_assignment_bounded",
            "skill_routes_selected",
            "tool_plan_governed",
            "safety_layer_checked",
        ]
        if tool_plan.get("blocked_tools"):
            checks.append("blocked_tools_waiting_for_approval")
        if analysis.get("risk_level") in {"high", "critical"}:
            checks.extend(["audit_log_required", "rollback_required", "rate_limit_required"])
        return {
            "checks": checks,
            "blocked": safety.get("requires_approval", False),
            "reason": safety.get("reason", "ok"),
            "confidence": round(max(0.25, 1.0 - float(analysis.get("uncertainty_score", 0.5)) * 0.5), 3),
        }

    def _learning_update(self, analysis: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        return {
            "memory_category": "task_history",
            "skill_learning_candidate": analysis["intent"],
            "failure_tracking": "enabled" if verification.get("blocked") else "watch",
            "experience_schema": [
                "task",
                "goal",
                "actions_taken",
                "tools_used",
                "agents_used",
                "errors",
                "successful_steps",
                "time_taken",
                "feedback",
                "score",
            ],
        }

    def _decode(self, row: Any, deduplicated: bool = False) -> dict[str, Any]:
        data = dict(row)
        for key in ["execution_tree", "verification", "learning_update", "dashboard_update"]:
            data[key] = loads(data.get(key), {})
        data["approved"] = bool(data.get("approved"))
        data["deduplicated"] = deduplicated
        return data
