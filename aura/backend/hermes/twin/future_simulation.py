from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from .digital_twin import CognitiveDigitalTwinEngine


class FutureSimulationEngine:
    """Simulates possible futures using Akansha's goal graph and digital twin."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.twin = CognitiveDigitalTwinEngine(store)

    def simulate(
        self,
        prompt: str,
        scenarios: list[str] | None = None,
        owner: str = "Yogesh",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_prompt = re.sub(r"\s+", " ", prompt.strip())
        if not clean_prompt:
            raise ValueError("Future simulation prompt cannot be empty")
        profile = self.twin.profile(owner)
        context = context or {}
        candidate_scenarios = scenarios or self._scenario_templates(clean_prompt)
        scored = [self._score_scenario(clean_prompt, scenario, profile, context) for scenario in candidate_scenarios]
        scored.sort(key=lambda item: (-item["decision_rank"], item["risk_score"]))
        risk_heatmap = self._risk_heatmap(scored, clean_prompt, profile)
        timeline_projection = self._timeline_projection(scored)
        behavior_trends = profile.get("behavior_trends", [])
        confidence = round(sum(item["confidence_score"] for item in scored) / max(1, len(scored)), 4)
        simulation = {
            "prompt": clean_prompt,
            "owner": owner,
            "scenarios": scored,
            "best_scenario": scored[0] if scored else {},
            "risk_heatmap": risk_heatmap,
            "goal_forecast": self._goal_forecast(clean_prompt, scored, profile),
            "decision_comparison": self._decision_comparison(scored),
            "timeline_projection": timeline_projection,
            "behavior_trends": behavior_trends,
            "opportunity_prediction": self._opportunities(clean_prompt, scored, profile),
            "confidence": confidence,
        }
        return self._store(simulation, context)

    def latest(self, owner: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        query = "SELECT * FROM future_simulations"
        params: list[Any] = []
        if owner:
            query += " WHERE owner = ?"
            params.append(owner)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 100)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode(row) for row in rows]

    def _scenario_templates(self, prompt: str) -> list[str]:
        lowered = prompt.lower()
        if re.search(r"\b(startup|business|launch|company)\b", lowered):
            return ["Build MVP first", "Build audience first", "Sell services first"]
        if re.search(r"\b(laptop|buy|purchase|headphones|phone)\b", lowered):
            return ["Choose higher performance option", "Choose lower price option", "Wait for better deal and verify price"]
        if re.search(r"\b(schedule|week|deadline|plan)\b", lowered):
            return ["Front-load testing and hard work", "Evenly distribute tasks", "Delay risky tasks until late week"]
        if re.search(r"\b(study|exam|learn|placement)\b", lowered):
            return ["Practice weak topics first", "Follow syllabus order", "Take mock tests first"]
        if re.search(r"\b(deploy|production|github|server)\b", lowered):
            return ["Run tests and environment validation first", "Deploy immediately with rollback", "Stage release then production"]
        return ["Fast execution path", "Quality-first path", "Low-risk validation path"]

    def _score_scenario(self, prompt: str, scenario: str, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        text = f"{prompt} {scenario}".lower()
        verification_preference = bool(profile.get("productivity_patterns"))
        comparison_preference = bool(profile.get("decision_history"))
        deadline_pressure = bool(re.search(r"\b(tomorrow|today|deadline|week|month)\b", text))
        is_quality = bool(re.search(r"\b(test|quality|verify|validated|stage|mvp|practice)\b", text))
        is_fast = bool(re.search(r"\bfast|immediate|quick|first\b", text))
        is_risky = bool(re.search(r"\bdelay|late|immediate|payment|production|unverified\b", text))
        resource_pressure = float(context.get("resource_pressure", min(1.0, float(context.get("complexity_score", 40) or 40) / 100)))

        success_probability = 0.58
        success_probability += 0.11 if is_quality else 0.0
        success_probability += 0.07 if is_fast and not is_risky else 0.0
        success_probability += 0.06 if verification_preference and is_quality else 0.0
        success_probability += 0.04 if comparison_preference and "compare" in text else 0.0
        success_probability -= 0.1 if is_risky and not is_quality else 0.0
        success_probability -= min(0.1, resource_pressure * 0.08)

        risk_score = 0.28 + (0.18 if is_risky else 0.0) + (0.08 if deadline_pressure else 0.0) + resource_pressure * 0.08
        risk_score -= 0.1 if is_quality else 0.0
        timeline_estimate = 0.45 + (0.16 if is_quality else 0.0) + (0.12 if resource_pressure > 0.65 else 0.0) - (0.08 if is_fast else 0.0)
        resource_estimate = 0.42 + resource_pressure * 0.22 + (0.08 if is_quality else 0.0)
        confidence_score = 0.68 + (0.09 if profile.get("confidence", 0) >= 0.72 else 0.0) + (0.05 if is_quality else 0.0)
        impact_score = 0.56 + (0.14 if re.search(r"\b(startup|launch|exam|deploy|buy|goal)\b", text) else 0.0)

        success_probability = self._clamp(success_probability)
        risk_score = self._clamp(risk_score)
        timeline_estimate = self._clamp(timeline_estimate)
        resource_estimate = self._clamp(resource_estimate)
        confidence_score = self._clamp(confidence_score)
        impact_score = self._clamp(impact_score)
        decision_rank = round(success_probability * 0.34 + (1 - risk_score) * 0.24 + impact_score * 0.22 + (1 - resource_estimate) * 0.12 + confidence_score * 0.08, 4)
        return {
            "scenario": scenario,
            "success_probability": round(success_probability, 4),
            "risk_score": round(risk_score, 4),
            "timeline_estimate": round(timeline_estimate, 4),
            "resource_estimate": round(resource_estimate, 4),
            "confidence_score": round(confidence_score, 4),
            "impact_score": round(impact_score, 4),
            "decision_rank": decision_rank,
            "predicted_outcomes": self._outcomes(scenario, success_probability, risk_score, deadline_pressure),
            "personal_fit": self._personal_fit(scenario, profile),
        }

    def _outcomes(self, scenario: str, success: float, risk: float, deadline_pressure: bool) -> list[str]:
        outcomes = [f"{scenario}: estimated success {round(success * 100)}% with risk {round(risk * 100)}%."]
        if risk >= 0.55:
            outcomes.append("Needs earlier validation, rollback plan, and user confirmation before execution.")
        if deadline_pressure:
            outcomes.append("Timeline pressure detected; move uncertain tasks earlier to prevent overload.")
        if success >= 0.75:
            outcomes.append("Strong candidate for proactive recommendation.")
        return outcomes

    def _personal_fit(self, scenario: str, profile: dict[str, Any]) -> dict[str, Any]:
        lowered = scenario.lower()
        fit = 0.62
        reasons: list[str] = []
        if "test" in lowered or "verify" in lowered or "quality" in lowered:
            fit += 0.14
            reasons.append("matches user's repeated recheck-and-verify preference")
        if "performance" in lowered and any("coding" in item["content"].lower() or "ai" in item["content"].lower() for item in profile.get("projects", [])):
            fit += 0.08
            reasons.append("matches coding and AI workload patterns")
        if "delay" in lowered or "late" in lowered:
            fit -= 0.12
            reasons.append("conflicts with observed delay/testing risk")
        return {"score": round(self._clamp(fit), 4), "reasons": reasons or ["limited personal evidence; use normal validation"]}

    def _risk_heatmap(self, scored: list[dict[str, Any]], prompt: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
        heatmap = [
            {"area": "timeline", "risk": max([item["timeline_estimate"] for item in scored], default=0.4), "reason": "estimated schedule pressure"},
            {"area": "execution", "risk": max([item["risk_score"] for item in scored], default=0.35), "reason": "highest scenario execution risk"},
            {"area": "resources", "risk": max([item["resource_estimate"] for item in scored], default=0.4), "reason": "time, attention, tool, or budget pressure"},
        ]
        if re.search(r"\b(latest|current|live|price|news|score)\b", prompt.lower()):
            heatmap.append({"area": "accuracy", "risk": 0.68, "reason": "live data must be verified from current sources"})
        if profile.get("productivity_patterns"):
            heatmap.append({"area": "validation", "risk": 0.46, "reason": "user expects strong recheck behavior before completion"})
        return heatmap

    def _goal_forecast(self, prompt: str, scored: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
        best = scored[0] if scored else {}
        return {
            "forecast": "positive_with_validation" if best.get("success_probability", 0) >= 0.7 else "needs_planning_before_execution",
            "best_path": best.get("scenario", ""),
            "completion_probability": best.get("success_probability", 0),
            "personal_context_used": {
                "projects": len(profile.get("projects", [])),
                "habits": len(profile.get("habits", [])),
                "work_patterns": len(profile.get("work_patterns", [])),
            },
        }

    def _decision_comparison(self, scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "rank": index,
                "scenario": item["scenario"],
                "success": item["success_probability"],
                "risk": item["risk_score"],
                "timeline": item["timeline_estimate"],
                "decision_rank": item["decision_rank"],
            }
            for index, item in enumerate(scored, start=1)
        ]

    def _timeline_projection(self, scored: list[dict[str, Any]]) -> dict[str, Any]:
        best = scored[0] if scored else {}
        load = best.get("timeline_estimate", 0.45)
        if load >= 0.75:
            bucket = "long_or_high_pressure"
        elif load >= 0.5:
            bucket = "medium"
        else:
            bucket = "short"
        return {
            "bucket": bucket,
            "relative_estimate": load,
            "suggested_pacing": "front_load_risky_work" if load >= 0.55 else "normal_pacing",
        }

    def _opportunities(self, prompt: str, scored: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
        opportunities: list[dict[str, Any]] = []
        best = scored[0] if scored else {}
        if best:
            opportunities.append({"type": "best_path", "message": f"Prefer '{best['scenario']}' because it has the strongest decision rank.", "confidence": best["confidence_score"]})
        if re.search(r"\b(startup|launch|project)\b", prompt.lower()):
            opportunities.append({"type": "strategic", "message": "Convert this into a tracked goal with weekly milestones and risk checks.", "confidence": 0.82})
        if profile.get("productivity_patterns"):
            opportunities.append({"type": "personal_optimization", "message": "Schedule validation earlier because the user repeatedly asks for rechecks.", "confidence": 0.8})
        return opportunities

    def _store(self, simulation: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        fingerprint = stable_fingerprint(
            f"future-simulation:{simulation['owner']}:{simulation['prompt']}:{'|'.join(item['scenario'] for item in simulation['scenarios'])}"
        )
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM future_simulations WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing)
            simulation_id = f"future_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO future_simulations(
                    id, owner, prompt, scenarios, best_scenario, risk_heatmap,
                    goal_forecast, decision_comparison, timeline_projection,
                    behavior_trends, opportunity_prediction, confidence, context,
                    fingerprint, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    simulation["owner"],
                    simulation["prompt"],
                    dumps(simulation["scenarios"]),
                    dumps(simulation["best_scenario"]),
                    dumps(simulation["risk_heatmap"]),
                    dumps(simulation["goal_forecast"]),
                    dumps(simulation["decision_comparison"]),
                    dumps(simulation["timeline_projection"]),
                    dumps(simulation["behavior_trends"]),
                    dumps(simulation["opportunity_prediction"]),
                    simulation["confidence"],
                    dumps(context),
                    fingerprint,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM future_simulations WHERE id = ?", (simulation_id,)).fetchone()
        return self._decode(row)

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in (
            "scenarios",
            "best_scenario",
            "risk_heatmap",
            "goal_forecast",
            "decision_comparison",
            "timeline_projection",
            "behavior_trends",
            "opportunity_prediction",
            "context",
        ):
            data[key] = loads(data.get(key), [] if key != "context" else {})
        return data

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
