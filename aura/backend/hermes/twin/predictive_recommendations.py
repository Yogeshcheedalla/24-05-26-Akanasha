from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class PredictiveRecommendationEngine:
    """Turns simulations into proactive but governed recommendations."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def recommend(
        self,
        task: str,
        twin_profile: dict[str, Any],
        simulation: dict[str, Any],
        analysis: dict[str, Any] | None = None,
        owner: str = "Yogesh",
    ) -> dict[str, Any]:
        analysis = analysis or {}
        actions = self._actions(task, simulation, analysis)
        risk_alerts = self._risk_alerts(task, simulation)
        optimizations = self._optimizations(twin_profile, simulation)
        goal_improvements = self._goal_improvements(task, simulation, analysis)
        confidence = self._confidence(actions, risk_alerts, simulation)
        payload = {
            "owner": owner,
            "task": task,
            "proactive_actions": actions,
            "risk_alerts": risk_alerts,
            "optimization_suggestions": optimizations,
            "goal_improvements": goal_improvements,
            "confidence": confidence,
            "source_simulation_id": simulation.get("id", ""),
            "requires_approval_before_execution": True,
        }
        return self._store(payload)

    def latest(self, owner: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        query = "SELECT * FROM predictive_recommendations"
        params: list[Any] = []
        if owner:
            query += " WHERE owner = ?"
            params.append(owner)
        query += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 100)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode(row) for row in rows]

    def _actions(self, task: str, simulation: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
        best = simulation.get("best_scenario") or {}
        actions: list[dict[str, Any]] = []
        if best:
            actions.append(
                {
                    "action": f"Use the '{best.get('scenario')}' path first.",
                    "reason": "It has the highest simulated decision rank.",
                    "confidence": best.get("confidence_score", 0.72),
                    "approval_required": False,
                }
            )
        lowered = task.lower()
        if re.search(r"\b(startup|goal|launch|months?)\b", lowered):
            actions.append(
                {
                    "action": "Convert the request into a goal graph with weekly milestones.",
                    "reason": "Long-horizon goals need progress tracking and blocker detection.",
                    "confidence": 0.84,
                    "approval_required": False,
                }
            )
        if re.search(r"\b(buy|book|purchase|payment|submit)\b", lowered) or analysis.get("risk_level") in {"high", "critical"}:
            actions.append(
                {
                    "action": "Pause before irreversible execution and ask for owner confirmation.",
                    "reason": "Safety policy forbids purchases, bookings, submissions, or sensitive actions without approval.",
                    "confidence": 0.95,
                    "approval_required": True,
                }
            )
        return actions[:6]

    def _risk_alerts(self, task: str, simulation: dict[str, Any]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for area in simulation.get("risk_heatmap", []):
            if float(area.get("risk", 0.0)) >= 0.55:
                alerts.append(
                    {
                        "area": area.get("area"),
                        "message": area.get("reason"),
                        "severity": "high" if float(area.get("risk", 0.0)) >= 0.7 else "medium",
                        "confidence": min(0.9, float(area.get("risk", 0.0)) + 0.15),
                    }
                )
        if re.search(r"\b(latest|live|current|news|price|score)\b", task.lower()):
            alerts.append(
                {
                    "area": "freshness",
                    "message": "Live facts must be checked with timestamps before confident output.",
                    "severity": "high",
                    "confidence": 0.9,
                }
            )
        return alerts[:8]

    def _optimizations(self, twin_profile: dict[str, Any], simulation: dict[str, Any]) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        if twin_profile.get("productivity_patterns"):
            suggestions.append(
                {
                    "suggestion": "Move testing and verification earlier in the workflow.",
                    "reason": "The digital twin shows repeated demand for recheck behavior.",
                    "confidence": 0.82,
                }
            )
        if twin_profile.get("decision_history"):
            suggestions.append(
                {
                    "suggestion": "Present decisions as ranked comparisons with long-term value, risk, and timeline.",
                    "reason": "The user repeatedly asks for comparison and accurate decision-making.",
                    "confidence": 0.8,
                }
            )
        timeline = simulation.get("timeline_projection", {})
        if timeline.get("suggested_pacing") == "front_load_risky_work":
            suggestions.append(
                {
                    "suggestion": "Front-load risky work instead of leaving it near the deadline.",
                    "reason": "The simulation predicts medium or high timeline pressure.",
                    "confidence": 0.78,
                }
            )
        return suggestions[:6]

    def _goal_improvements(self, task: str, simulation: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
        improvements: list[dict[str, Any]] = []
        if analysis.get("intent") == "goal_management" or re.search(r"\b(startup|project|goal|milestone)\b", task.lower()):
            improvements.append(
                {
                    "improvement": "Add explicit success metrics, weekly milestones, owner checkpoints, and blocker reviews.",
                    "confidence": 0.83,
                }
            )
        best = simulation.get("best_scenario") or {}
        if best:
            improvements.append(
                {
                    "improvement": f"Use '{best.get('scenario')}' as the primary plan and keep the second-ranked path as fallback.",
                    "confidence": best.get("confidence_score", 0.72),
                }
            )
        return improvements[:6]

    def _confidence(self, actions: list[dict[str, Any]], risk_alerts: list[dict[str, Any]], simulation: dict[str, Any]) -> float:
        values = [float(item.get("confidence", 0.7)) for item in actions + risk_alerts]
        values.append(float(simulation.get("confidence", 0.7)))
        return round(sum(values) / max(1, len(values)), 4)

    def _store(self, payload: dict[str, Any]) -> dict[str, Any]:
        fingerprint = stable_fingerprint(f"predictive-recommendation:{payload['owner']}:{payload['task']}:{payload.get('source_simulation_id')}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM predictive_recommendations WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing)
            rec_id = f"prec_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO predictive_recommendations(
                    id, owner, task, proactive_actions, risk_alerts,
                    optimization_suggestions, goal_improvements, confidence,
                    source_simulation_id, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    rec_id,
                    payload["owner"],
                    payload["task"],
                    dumps(payload["proactive_actions"]),
                    dumps(payload["risk_alerts"]),
                    dumps(payload["optimization_suggestions"]),
                    dumps(payload["goal_improvements"]),
                    payload["confidence"],
                    payload.get("source_simulation_id", ""),
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM predictive_recommendations WHERE id = ?", (rec_id,)).fetchone()
        return self._decode(row)

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("proactive_actions", "risk_alerts", "optimization_suggestions", "goal_improvements"):
            data[key] = loads(data.get(key), [])
        return data
