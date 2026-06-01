from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..action_platform.metrics import ActionPlatformMetrics
from ..database.store import CognitiveStore, dumps, loads, utc_now


class CognitiveObservatoryDashboard:
    """Builds a compact live operating snapshot from the existing Hermes store."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def snapshot(self, runtime_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            active_goals = [self._decode(row) for row in conn.execute(
                "SELECT * FROM goals WHERE status IN ('active', 'blocked') ORDER BY priority DESC, updated_at DESC LIMIT 8"
            ).fetchall()]
            active_agents = [self._decode_agent(row) for row in conn.execute(
                "SELECT * FROM agents WHERE status = 'active' ORDER BY last_active DESC LIMIT 12"
            ).fetchall()]
            recent_workflows = [self._decode_workflow(row) for row in conn.execute(
                "SELECT * FROM workflow_templates ORDER BY updated_at DESC LIMIT 8"
            ).fetchall()]
            recent_explanations = [self._decode(row) for row in conn.execute(
                "SELECT * FROM action_explanations ORDER BY created_at DESC LIMIT 8"
            ).fetchall()]
            recent_experiments = [self._decode(row) for row in conn.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC LIMIT 6"
            ).fetchall()]
            recent_tests = [self._decode(row) for row in conn.execute(
                "SELECT * FROM autonomous_test_reports ORDER BY created_at DESC LIMIT 6"
            ).fetchall()]
            recent_executions = [self._decode(row) for row in conn.execute(
                "SELECT * FROM universal_executions ORDER BY created_at DESC LIMIT 8"
            ).fetchall()]
            pending_questions = [self._decode(row) for row in conn.execute(
                "SELECT * FROM collaboration_questions WHERE status = 'awaiting_user' ORDER BY created_at DESC LIMIT 8"
            ).fetchall()]
            recent_recovery = [self._decode(row) for row in conn.execute(
                "SELECT * FROM self_healing_events ORDER BY created_at DESC LIMIT 8"
            ).fetchall()]
            proactive_events = [self._decode(row) for row in conn.execute(
                "SELECT * FROM proactive_events ORDER BY priority DESC, created_at DESC LIMIT 8"
            ).fetchall()]
            automation_plans = [self._decode(row) for row in conn.execute(
                "SELECT * FROM automation_plans ORDER BY created_at DESC LIMIT 8"
            ).fetchall()]
            cognitive_health_rows = [self._decode(row) for row in conn.execute(
                "SELECT * FROM cognitive_health_snapshots ORDER BY created_at DESC LIMIT 3"
            ).fetchall()]
            digital_twin_profile = self._decode(conn.execute(
                "SELECT * FROM digital_twin_profiles ORDER BY updated_at DESC LIMIT 1"
            ).fetchone())
            future_predictions = [self._decode(row) for row in conn.execute(
                "SELECT * FROM future_simulations ORDER BY created_at DESC LIMIT 6"
            ).fetchall()]
            predictive_recommendations = [self._decode(row) for row in conn.execute(
                "SELECT * FROM predictive_recommendations ORDER BY confidence DESC, created_at DESC LIMIT 6"
            ).fetchall()]
            goal_task_counts = self._goal_task_counts(conn)
        with self.store.connect(self.store.files.experiences) as conn:
            failures = conn.execute("SELECT COUNT(*) AS count FROM failure_lessons WHERE status = 'active'").fetchone()["count"]
        with self.store.connect(self.store.files.skills) as conn:
            skill_count = conn.execute("SELECT COUNT(*) AS count FROM skills").fetchone()["count"]
            stable_skill_count = conn.execute("SELECT COUNT(*) AS count FROM skills WHERE status = 'stable'").fetchone()["count"]
        memory_usage = self._memory_usage()
        skills_triggered = self._skills_triggered()
        task_graph = self._task_execution_graph(active_goals, recent_workflows, goal_task_counts)
        health = self._health_score(active_goals, failures, recent_tests)
        learning = self._learning_progress(skill_count, stable_skill_count, memory_usage, failures)
        token_usage = self._estimate_tokens(memory_usage, recent_workflows, recent_explanations, runtime_metrics)
        action_platform = ActionPlatformMetrics(self.store).snapshot()
        snapshot = {
            "active_goals": active_goals,
            "active_agents": active_agents,
            "skills_triggered": skills_triggered,
            "memory_usage": memory_usage,
            "task_execution_graph": task_graph,
            "prediction_confidence": self._prediction_confidence(active_goals, recent_explanations),
            "system_health": health,
            "token_usage": token_usage,
            "learning_progress": learning,
            "action_platform": action_platform,
            "universal_execution": {
                "recent": recent_executions,
                "pending_collaboration": pending_questions,
                "recovery_actions": recent_recovery,
                "proactive_events": proactive_events,
                "automation_plans": automation_plans,
                "cognitive_health": cognitive_health_rows[0] if cognitive_health_rows else {},
            },
            "digital_twin": {
                "profile": digital_twin_profile or {},
                "future_predictions": future_predictions,
                "risk_heatmaps": [item.get("risk_heatmap", []) for item in future_predictions],
                "goal_forecasts": [item.get("goal_forecast", {}) for item in future_predictions],
                "decision_comparisons": [item.get("decision_comparison", []) for item in future_predictions],
                "timeline_projections": [item.get("timeline_projection", {}) for item in future_predictions],
                "behavior_trends": (digital_twin_profile or {}).get("behavior_trends", []),
                "recommendations": predictive_recommendations,
            },
            "experiments": recent_experiments,
            "autonomous_tests": recent_tests,
            "runtime_metrics": runtime_metrics or {},
            "created_at": utc_now(),
        }
        snapshot_id = f"observatory_{uuid4().hex}"
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO observatory_snapshots(id, snapshot, health_score, token_usage, learning_progress, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    dumps(snapshot),
                    health["score"],
                    token_usage["estimated_current_tokens"],
                    learning["score"],
                    snapshot["created_at"],
                ),
            )
        snapshot["id"] = snapshot_id
        return snapshot

    def latest(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM observatory_snapshots ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 50)),),
            ).fetchall()
        return [self._decode_snapshot(row) for row in rows]

    def _memory_usage(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.memories) as conn:
            long_rows = conn.execute(
                "SELECT category, COUNT(*) AS count FROM long_term_memories WHERE archived = 0 GROUP BY category"
            ).fetchall()
            short_count = conn.execute("SELECT COUNT(*) AS count FROM short_term_memory").fetchone()["count"]
            compression_count = conn.execute("SELECT COUNT(*) AS count FROM cognitive_compressions").fetchone()["count"]
        category_counts = {row["category"]: row["count"] for row in long_rows}
        total_long = sum(category_counts.values())
        return {
            "long_term_total": total_long,
            "short_term_total": short_count,
            "compressions": compression_count,
            "categories": category_counts,
            "compression_ratio_hint": round(compression_count / max(1, total_long), 3),
        }

    def _skills_triggered(self) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.skills) as conn:
            rows = conn.execute(
                """
                SELECT name, status, confidence, success_rate, usage_count, reward_score, version
                FROM skills
                ORDER BY usage_count DESC, reward_score DESC, updated_at DESC
                LIMIT 12
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _goal_task_counts(self, conn: Any) -> dict[str, dict[str, int]]:
        rows = conn.execute(
            "SELECT goal_id, status, COUNT(*) AS count FROM goal_tasks GROUP BY goal_id, status"
        ).fetchall()
        counts: dict[str, dict[str, int]] = {}
        for row in rows:
            counts.setdefault(row["goal_id"], {})[row["status"]] = row["count"]
        return counts

    def _task_execution_graph(
        self,
        goals: list[dict[str, Any]],
        workflows: list[dict[str, Any]],
        task_counts: dict[str, dict[str, int]],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for goal in goals:
            goal_id = goal["id"]
            nodes.append({"id": goal_id, "type": "goal", "label": goal["title"], "status": goal["status"]})
            for status, count in task_counts.get(goal_id, {}).items():
                task_node = f"{goal_id}:{status}"
                nodes.append({"id": task_node, "type": "task_bucket", "label": status, "count": count})
                edges.append({"source": goal_id, "target": task_node, "relationship": "contains"})
        for workflow in workflows:
            workflow_id = workflow["id"]
            nodes.append({"id": workflow_id, "type": "workflow", "label": workflow["name"], "intent": workflow["intent"]})
            for agent_type in workflow.get("agent_types", [])[:4]:
                agent_node = f"{workflow_id}:{agent_type}"
                nodes.append({"id": agent_node, "type": "agent_route", "label": agent_type})
                edges.append({"source": workflow_id, "target": agent_node, "relationship": "routes_to"})
        return {"nodes": nodes[:60], "edges": edges[:80]}

    def _health_score(self, goals: list[dict[str, Any]], active_failures: int, tests: list[dict[str, Any]]) -> dict[str, Any]:
        blocked_goals = sum(1 for goal in goals if goal.get("status") == "blocked")
        failed_tests = sum(1 for report in tests if report.get("status") == "failed")
        score = 1.0 - min(0.7, blocked_goals * 0.08 + active_failures * 0.03 + failed_tests * 0.08)
        status = "healthy" if score >= 0.82 else "watch" if score >= 0.62 else "needs_attention"
        return {
            "status": status,
            "score": round(max(0.0, score), 3),
            "blocked_goals": blocked_goals,
            "active_failure_lessons": active_failures,
            "failed_test_reports": failed_tests,
        }

    def _learning_progress(
        self,
        skill_count: int,
        stable_skill_count: int,
        memory_usage: dict[str, Any],
        active_failures: int,
    ) -> dict[str, Any]:
        stability = stable_skill_count / max(1, skill_count)
        memory_signal = min(1.0, (memory_usage["long_term_total"] + memory_usage["compressions"]) / 25)
        failure_penalty = min(0.35, active_failures * 0.025)
        score = max(0.0, min(1.0, (stability * 0.45) + (memory_signal * 0.45) + 0.1 - failure_penalty))
        return {
            "score": round(score, 3),
            "stable_skills": stable_skill_count,
            "total_skills": skill_count,
            "memory_signal": round(memory_signal, 3),
            "failure_penalty": round(failure_penalty, 3),
        }

    def _prediction_confidence(self, goals: list[dict[str, Any]], explanations: list[dict[str, Any]]) -> dict[str, Any]:
        values = [float(goal.get("confidence", 0.7)) for goal in goals]
        values.extend(float(item.get("confidence", 0.7)) for item in explanations)
        avg = sum(values) / len(values) if values else 0.72
        return {
            "average": round(avg, 3),
            "source": "goal_graph_and_explainability",
            "sample_size": len(values),
        }

    def _estimate_tokens(
        self,
        memory_usage: dict[str, Any],
        workflows: list[dict[str, Any]],
        explanations: list[dict[str, Any]],
        runtime_metrics: dict[str, Any] | None,
    ) -> dict[str, Any]:
        workflow_text = dumps(workflows)
        explanation_text = dumps(explanations)
        estimated = int((len(workflow_text) + len(explanation_text)) / 4)
        estimated += memory_usage["long_term_total"] * 45 + memory_usage["short_term_total"] * 20
        metric_bonus = len(dumps(runtime_metrics or {})) // 4
        return {
            "estimated_current_tokens": estimated + metric_bonus,
            "context_capacity": 128000,
            "compression_hint": "compress memory when estimated context load crosses 70% capacity",
            "usage_ratio": round((estimated + metric_bonus) / 128000, 4),
        }

    def _decode_snapshot(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["snapshot"] = loads(data.get("snapshot"), {})
        return data

    def _decode_agent(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["goals"] = loads(data.get("goals"), [])
        data["tools"] = loads(data.get("tools"), [])
        data["communication_protocol"] = loads(data.get("communication_protocol"), {})
        return data

    def _decode_workflow(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["steps"] = loads(data.get("steps"), [])
        data["required_tools"] = loads(data.get("required_tools"), [])
        data["agent_types"] = loads(data.get("agent_types"), [])
        return data

    def _decode(self, row: Any) -> dict[str, Any]:
        if row is None:
            return {}
        data = dict(row)
        for key in (
            "milestones",
            "execution_state",
            "workflow_selection",
            "agent_selection",
            "skill_selection",
            "tool_selection",
            "payload",
            "variants",
            "execution_tree",
            "verification",
            "learning_update",
            "dashboard_update",
            "context",
            "root_cause",
            "recovery_plan",
            "surfaces",
            "action_plan",
            "required_permissions",
            "agent_activity",
            "tool_failures",
            "execution_latency",
            "workflow_efficiency",
            "resource_consumption",
            "hallucination_signals",
            "learning_quality",
            "habits",
            "preferences",
            "goals",
            "projects",
            "learning_patterns",
            "work_patterns",
            "decision_history",
            "execution_history",
            "productivity_patterns",
            "behavior_trends",
            "attributes",
            "scenarios",
            "best_scenario",
            "risk_heatmap",
            "goal_forecast",
            "decision_comparison",
            "timeline_projection",
            "opportunity_prediction",
            "context",
            "proactive_actions",
            "risk_alerts",
            "optimization_suggestions",
            "goal_improvements",
        ):
            if key in data:
                data[key] = loads(data.get(key), data.get(key))
        return data
