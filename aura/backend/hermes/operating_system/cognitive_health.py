from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, utc_now
from .common import clamp


class CognitiveHealthEngine:
    """Computes operating health across memory, agents, tools, learning, and workflows."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def snapshot(
        self,
        runtime_metrics: dict[str, Any] | None = None,
        analysis: dict[str, Any] | None = None,
        collaboration: dict[str, Any] | None = None,
        self_healing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime_metrics = runtime_metrics or {}
        analysis = analysis or {}
        collaboration = collaboration or {}
        self_healing = self_healing or {}
        memory_usage = self._memory_usage()
        agent_activity = self._agent_activity()
        tool_failures = self._tool_failures()
        execution_latency = self._latency(runtime_metrics, analysis)
        prediction_accuracy = self._prediction_accuracy(analysis)
        workflow_efficiency = self._workflow_efficiency(runtime_metrics, self_healing)
        resource_consumption = self._resource_consumption(runtime_metrics)
        hallucination_signals = self._hallucination_signals(collaboration, analysis)
        learning_quality = self._learning_quality()
        score = round(
            clamp(
                (
                    memory_usage["score"]
                    + agent_activity["score"]
                    + tool_failures["score"]
                    + execution_latency["score"]
                    + prediction_accuracy["score"]
                    + workflow_efficiency["score"]
                    + resource_consumption["score"]
                    + hallucination_signals["score"]
                    + learning_quality["score"]
                )
                / 9
            ),
            3,
        )
        status = "healthy" if score >= 0.9 else "watch" if score >= 0.72 else "needs_attention"
        snapshot = {
            "system_health": score,
            "status": status,
            "prediction_confidence": prediction_accuracy["score"],
            "memory_efficiency": memory_usage["score"],
            "agent_activity": agent_activity,
            "tool_failures": tool_failures,
            "execution_latency": execution_latency,
            "workflow_efficiency": workflow_efficiency,
            "resource_consumption": resource_consumption,
            "hallucination_signals": hallucination_signals,
            "learning_quality": learning_quality,
            "created_at": utc_now(),
        }
        with self.store.connect(self.store.files.agents) as conn:
            snapshot_id = f"chealth_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO cognitive_health_snapshots(
                    id, system_health, prediction_confidence, memory_efficiency,
                    agent_activity, tool_failures, execution_latency,
                    workflow_efficiency, resource_consumption, hallucination_signals,
                    learning_quality, payload, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    snapshot["system_health"],
                    snapshot["prediction_confidence"],
                    snapshot["memory_efficiency"],
                    dumps(agent_activity),
                    dumps(tool_failures),
                    dumps(execution_latency),
                    dumps(workflow_efficiency),
                    dumps(resource_consumption),
                    dumps(hallucination_signals),
                    dumps(learning_quality),
                    dumps(snapshot),
                    snapshot["created_at"],
                ),
            )
        snapshot["id"] = snapshot_id
        return snapshot

    def latest(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM cognitive_health_snapshots ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 50)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _memory_usage(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.memories) as conn:
            long_total = conn.execute("SELECT COUNT(*) AS count FROM long_term_memories WHERE archived = 0").fetchone()["count"]
            compressed = conn.execute("SELECT COUNT(*) AS count FROM cognitive_compressions").fetchone()["count"]
        score = clamp(0.82 + min(0.12, compressed * 0.01) - max(0, long_total - 500) * 0.0006)
        return {"score": round(score, 3), "long_term_total": long_total, "compressions": compressed}

    def _agent_activity(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            active = conn.execute("SELECT COUNT(*) AS count FROM agents WHERE status = 'active'").fetchone()["count"]
        score = clamp(0.7 + min(0.24, active * 0.025) - max(0, active - 10) * 0.03)
        return {"score": round(score, 3), "active_agents": active, "limit": 10}

    def _tool_failures(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.experiences) as conn:
            failures = conn.execute("SELECT COUNT(*) AS count FROM failure_lessons WHERE status = 'active'").fetchone()["count"]
        return {"score": round(clamp(1.0 - failures * 0.035), 3), "active_failure_lessons": failures}

    def _latency(self, runtime_metrics: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        average = float(runtime_metrics.get("average_latency_seconds", analysis.get("estimated_runtime", 1.0) or 1.0))
        score = clamp(1.0 - max(0.0, average - 1.0) * 0.08)
        return {"score": round(score, 3), "estimated_seconds": round(average, 3)}

    def _prediction_accuracy(self, analysis: dict[str, Any]) -> dict[str, Any]:
        uncertainty = float(analysis.get("uncertainty_score", 0.38) or 0.38)
        return {"score": round(clamp(1.0 - uncertainty * 0.45), 3), "uncertainty": uncertainty}

    def _workflow_efficiency(self, runtime_metrics: dict[str, Any], self_healing: dict[str, Any]) -> dict[str, Any]:
        recovery_penalty = 0.12 if self_healing.get("status") == "recovery_plan_ready" else 0.0
        blocked = float(runtime_metrics.get("tasks_blocked", 0))
        allowed = float(runtime_metrics.get("tasks_allowed", 1))
        blocked_ratio = blocked / max(1.0, blocked + allowed)
        return {"score": round(clamp(0.93 - recovery_penalty - blocked_ratio * 0.18), 3), "blocked_ratio": round(blocked_ratio, 3)}

    def _resource_consumption(self, runtime_metrics: dict[str, Any]) -> dict[str, Any]:
        counters = runtime_metrics.get("counters", {}) if isinstance(runtime_metrics.get("counters"), dict) else {}
        total_events = sum(float(value) for value in counters.values()) if counters else 0.0
        return {"score": round(clamp(0.96 - max(0.0, total_events - 100) * 0.001), 3), "counter_events": int(total_events)}

    def _hallucination_signals(self, collaboration: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        signals = 0
        if collaboration.get("needs_user_input"):
            signals += 1
        if analysis.get("intent") == "live_research" and "web_search" not in analysis.get("tools", []):
            signals += 1
        score = clamp(1.0 - signals * 0.18)
        return {"score": round(score, 3), "signals": signals}

    def _learning_quality(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.skills) as conn:
            total = conn.execute("SELECT COUNT(*) AS count FROM skills").fetchone()["count"]
            stable = conn.execute("SELECT COUNT(*) AS count FROM skills WHERE status = 'stable'").fetchone()["count"]
        score = clamp(0.78 + (stable / max(1, total)) * 0.18)
        return {"score": round(score, 3), "stable_skills": stable, "total_skills": total}

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in [
            "agent_activity",
            "tool_failures",
            "execution_latency",
            "workflow_efficiency",
            "resource_consumption",
            "hallucination_signals",
            "learning_quality",
            "payload",
        ]:
            data[key] = loads(data.get(key), {})
        return data
