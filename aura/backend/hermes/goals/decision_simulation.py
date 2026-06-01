from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class DecisionSimulationEngine:
    """Compares choices with bounded, explainable estimates."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def simulate(self, decision: str, choices: list[str], context: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_decision = re.sub(r"\s+", " ", decision.strip())
        clean_choices = [re.sub(r"\s+", " ", item.strip()) for item in choices if item.strip()]
        if not clean_decision:
            raise ValueError("Decision cannot be empty")
        if len(clean_choices) < 2:
            raise ValueError("At least two choices are required for decision simulation")
        context = context or {}
        ranked = [self._score_choice(choice, clean_decision, context) for choice in clean_choices]
        ranked.sort(key=lambda item: (-item["decision_rank"], item["risk_score"]))
        confidence = round(sum(item["confidence_score"] for item in ranked) / len(ranked), 4)
        fingerprint = stable_fingerprint(f"decision:{clean_decision}:{'|'.join(clean_choices)}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM decision_simulations WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing)
            simulation_id = f"decision_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO decision_simulations(
                    id, decision, choices, ranked_choices, context, confidence, fingerprint, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    clean_decision,
                    dumps(clean_choices),
                    dumps(ranked),
                    dumps(context),
                    confidence,
                    fingerprint,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM decision_simulations WHERE id = ?", (simulation_id,)).fetchone()
        return self._decode(row)

    def _score_choice(self, choice: str, decision: str, context: dict[str, Any]) -> dict[str, Any]:
        text = f"{choice} {decision}".lower()
        speed_bonus = 0.12 if re.search(r"\bfast|quick|simple|small|mvp|prototype\b", text) else 0.0
        quality_bonus = 0.12 if re.search(r"\bquality|production|stable|tested|secure\b", text) else 0.0
        risk_penalty = 0.18 if re.search(r"\brisky|delete|payment|unverified|manual|unknown\b", text) else 0.0
        cost_penalty = 0.1 if re.search(r"\bexpensive|cost|paid|large|complex\b", text) else 0.0
        impact_bonus = 0.14 if re.search(r"\blaunch|customer|revenue|deadline|exam|user\b", text) else 0.0
        resource_factor = float(context.get("resource_pressure", 0.4))
        risk_score = max(0.05, min(0.95, 0.32 + risk_penalty + cost_penalty + resource_factor * 0.12 - speed_bonus))
        success_probability = max(0.05, min(0.95, 0.62 + speed_bonus + quality_bonus + impact_bonus - risk_penalty - cost_penalty))
        resource_estimate = max(0.1, min(1.0, 0.45 + cost_penalty + resource_factor * 0.2 - speed_bonus))
        time_estimate = max(0.1, min(1.0, 0.5 + cost_penalty + risk_penalty - speed_bonus))
        impact_score = max(0.1, min(1.0, 0.55 + impact_bonus + quality_bonus))
        execution_complexity = max(0.1, min(1.0, 0.45 + cost_penalty + risk_penalty - speed_bonus / 2))
        decision_rank = round((success_probability * 0.35) + (impact_score * 0.25) + ((1 - risk_score) * 0.25) + ((1 - resource_estimate) * 0.15), 4)
        return {
            "choice": choice,
            "success_probability": round(success_probability, 4),
            "risk_score": round(risk_score, 4),
            "resource_estimate": round(resource_estimate, 4),
            "predicted_outcomes": self._outcomes(choice, success_probability, risk_score),
            "confidence_score": round(max(0.55, min(0.92, 0.76 + quality_bonus - risk_penalty / 2)), 4),
            "time_estimate": round(time_estimate, 4),
            "cost_estimate": round(resource_estimate, 4),
            "impact_score": round(impact_score, 4),
            "execution_complexity": round(execution_complexity, 4),
            "decision_rank": decision_rank,
        }

    def _outcomes(self, choice: str, success: float, risk: float) -> list[str]:
        outcomes = [f"{choice} has an estimated {round(success * 100)}% success probability."]
        if risk > 0.55:
            outcomes.append("Requires validation and rollback planning before execution.")
        else:
            outcomes.append("Can proceed with normal validation gates.")
        return outcomes

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["choices"] = loads(data.get("choices"), [])
        data["ranked_choices"] = loads(data.get("ranked_choices"), [])
        data["context"] = loads(data.get("context"), {})
        return data
