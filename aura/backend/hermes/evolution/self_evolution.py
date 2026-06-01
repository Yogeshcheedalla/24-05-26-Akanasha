from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, utc_now


class SelfEvolutionEngine:
    """Produces bounded optimization proposals without mutating stable systems automatically."""

    AREAS = ("prompt_quality", "memory_retrieval", "workflow_order", "tool_selection", "agent_allocation")

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def optimize(self, task: str = "", runtime_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        metrics = self._collect_metrics(runtime_metrics or {})
        events = [
            self._proposal("prompt_quality", self._prompt_recommendation(task, metrics), metrics),
            self._proposal("memory_retrieval", self._memory_recommendation(metrics), metrics),
            self._proposal("workflow_order", self._workflow_recommendation(metrics), metrics),
            self._proposal("tool_selection", self._tool_recommendation(metrics), metrics),
            self._proposal("agent_allocation", self._agent_recommendation(metrics), metrics),
        ]
        return {
            "status": "proposed",
            "policy": "validation_required_before_promotion",
            "task": task,
            "events": events,
            "metrics": metrics,
        }

    def promote(self, event_id: str) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM self_evolution_events WHERE id = ?", (event_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown self-evolution event: {event_id}")
            if row["confidence"] < 0.82:
                raise ValueError("Self-evolution proposal confidence is too low for promotion")
            now = utc_now()
            conn.execute(
                "UPDATE self_evolution_events SET status = 'promoted', updated_at = ? WHERE id = ?",
                (now, event_id),
            )
            updated = conn.execute("SELECT * FROM self_evolution_events WHERE id = ?", (event_id,)).fetchone()
        return self._decode(updated)

    def list_events(self, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        sql = "SELECT * FROM self_evolution_events"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 100)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._decode(row) for row in rows]

    def _collect_metrics(self, runtime_metrics: dict[str, Any]) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            workflow_count = conn.execute("SELECT COUNT(*) AS count FROM workflow_templates").fetchone()["count"]
            active_agent_count = conn.execute("SELECT COUNT(*) AS count FROM agents WHERE status = 'active'").fetchone()["count"]
            active_goal_count = conn.execute("SELECT COUNT(*) AS count FROM goals WHERE status IN ('active', 'blocked')").fetchone()["count"]
            failed_tests = conn.execute("SELECT COUNT(*) AS count FROM autonomous_test_reports WHERE status = 'failed'").fetchone()["count"]
        with self.store.connect(self.store.files.memories) as conn:
            memory_count = conn.execute("SELECT COUNT(*) AS count FROM long_term_memories WHERE archived = 0").fetchone()["count"]
        with self.store.connect(self.store.files.experiences) as conn:
            experience_count = conn.execute("SELECT COUNT(*) AS count FROM experiences").fetchone()["count"]
            failure_count = conn.execute("SELECT COUNT(*) AS count FROM failure_lessons WHERE status = 'active'").fetchone()["count"]
        return {
            "workflow_count": workflow_count,
            "active_agent_count": active_agent_count,
            "active_goal_count": active_goal_count,
            "memory_count": memory_count,
            "experience_count": experience_count,
            "failure_count": failure_count,
            "failed_tests": failed_tests,
            "runtime": runtime_metrics,
        }

    def _proposal(self, area: str, recommendation: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        event_id = f"evolution_{uuid4().hex}"
        confidence = recommendation["confidence"]
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO self_evolution_events(
                    id, area, recommendation, before_state, after_state, confidence,
                    status, metrics, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?)
                """,
                (
                    event_id,
                    area,
                    recommendation["recommendation"],
                    dumps(recommendation["before_state"]),
                    dumps(recommendation["after_state"]),
                    confidence,
                    dumps(metrics),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM self_evolution_events WHERE id = ?", (event_id,)).fetchone()
        return self._decode(row)

    def _prompt_recommendation(self, task: str, metrics: dict[str, Any]) -> dict[str, Any]:
        needs_precision = any(word in task.lower() for word in ["latest", "accurate", "pdf", "report", "test"])
        confidence = 0.84 if needs_precision else 0.76
        return {
            "recommendation": "Add explicit output contract, source validation, and refusal-to-guess clauses to task prompts.",
            "before_state": {"style": "task_only", "precision_requested": needs_precision},
            "after_state": {"style": "contract_plus_validation", "requires_sources": needs_precision},
            "confidence": confidence,
        }

    def _memory_recommendation(self, metrics: dict[str, Any]) -> dict[str, Any]:
        memory_pressure = metrics["memory_count"] > 30
        return {
            "recommendation": "Run weighted recall with compression before planning; archive low-confidence duplicate memory.",
            "before_state": {"memory_count": metrics["memory_count"], "compression": "periodic"},
            "after_state": {"memory_count": metrics["memory_count"], "compression": "pre_plan_when_pressure_high"},
            "confidence": 0.86 if memory_pressure else 0.78,
        }

    def _workflow_recommendation(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return {
            "recommendation": "Place validation before user-facing artifact links and record replay event after every workflow.",
            "before_state": {"workflow_count": metrics["workflow_count"], "validation_position": "late"},
            "after_state": {"validation_position": "pre_response", "replay_recording": "enabled"},
            "confidence": 0.88,
        }

    def _tool_recommendation(self, metrics: dict[str, Any]) -> dict[str, Any]:
        confidence = 0.82 if metrics["failure_count"] else 0.75
        return {
            "recommendation": "Prefer trusted domain-specific tools before generic browser search for live or high-stakes facts.",
            "before_state": {"active_failures": metrics["failure_count"], "selection": "capability_match"},
            "after_state": {"selection": "capability_plus_trust_ranking"},
            "confidence": confidence,
        }

    def _agent_recommendation(self, metrics: dict[str, Any]) -> dict[str, Any]:
        pressure = metrics["active_goal_count"] + metrics["failed_tests"]
        return {
            "recommendation": "Use core agents for simple tasks; add TestingAgent and QualityAgent whenever regression risk appears.",
            "before_state": {"active_agents": metrics["active_agent_count"], "goal_pressure": pressure},
            "after_state": {"worker_policy": "risk_weighted", "max_temporary_workers": 6},
            "confidence": 0.85 if pressure else 0.79,
        }

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["before_state"] = loads(data.get("before_state"), {})
        data["after_state"] = loads(data.get("after_state"), {})
        data["metrics"] = loads(data.get("metrics"), {})
        return data

