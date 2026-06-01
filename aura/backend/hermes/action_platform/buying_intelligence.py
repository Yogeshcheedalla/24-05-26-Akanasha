from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from .common import clamp, extract_budget


class PersonalBuyingIntelligence:
    """Learns non-sensitive buying preferences without executing purchases."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def profile(self, owner: str = "Yogesh") -> dict[str, Any]:
        fingerprint = stable_fingerprint(f"buying:{owner}")
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute(
                "SELECT * FROM buying_intelligence_profiles WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if row:
                return self._decode(row)
            now = utc_now()
            profile_id = f"buying_{uuid4().hex}"
            defaults = {
                "preferences": {"default_tradeoff": "balanced_value", "privacy": "do_not_store_payment_details"},
                "budget_patterns": {"preferred_constraint": "ask_if_missing", "average_budget": None},
                "brand_preferences": {},
                "purchase_history": [],
                "risk_tolerance": {"price_risk": "low", "quality_risk": "low", "delivery_risk": "medium"},
                "insights": ["Ask for approval before every purchase", "Prefer source-verified prices over memory guesses"],
            }
            conn.execute(
                """
                INSERT INTO buying_intelligence_profiles(
                    id, owner, preferences, budget_patterns, brand_preferences,
                    purchase_history, risk_tolerance, insights, confidence,
                    fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    owner,
                    dumps(defaults["preferences"]),
                    dumps(defaults["budget_patterns"]),
                    dumps(defaults["brand_preferences"]),
                    dumps(defaults["purchase_history"]),
                    dumps(defaults["risk_tolerance"]),
                    dumps(defaults["insights"]),
                    0.78,
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM buying_intelligence_profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._decode(row)

    def learn_from_intent(self, user_intent: str, owner: str = "Yogesh") -> dict[str, Any]:
        profile = self.profile(owner)
        budget = extract_budget(user_intent)
        insights = list(profile["insights"])
        if budget["amount"] is not None:
            profile["budget_patterns"]["last_budget"] = budget
            insights.append(f"Recent budget signal: {budget['currency']} {budget['amount']:.0f} maximum")
        if "battery" in user_intent.lower():
            insights.append("User showed interest in battery life for device comparisons")
        profile["insights"] = list(dict.fromkeys(insights))[-12:]
        profile["confidence"] = round(clamp(float(profile["confidence"]) + 0.02, 0.0, 0.94), 3)
        self._persist(profile)
        return profile

    def recommend_bias(self, requirements: dict[str, Any], owner: str = "Yogesh") -> dict[str, Any]:
        profile = self.profile(owner)
        priorities = requirements.get("priorities", [])
        bias = {
            "price_weight": 0.28,
            "quality_weight": 0.28,
            "review_weight": 0.2,
            "delivery_weight": 0.12,
            "history_weight": 0.12,
        }
        if "lowest_price" in priorities:
            bias["price_weight"] += 0.12
            bias["quality_weight"] -= 0.06
        if "battery_life" in priorities or "quality" in priorities:
            bias["quality_weight"] += 0.1
            bias["price_weight"] -= 0.04
        if profile["risk_tolerance"].get("delivery_risk") == "low":
            bias["delivery_weight"] += 0.04
        return {"owner": owner, "bias": bias, "profile_insights": profile["insights"], "confidence": profile["confidence"]}

    def update_preferences(self, owner: str, preferences: dict[str, Any]) -> dict[str, Any]:
        profile = self.profile(owner)
        profile["preferences"].update(preferences)
        profile["insights"] = list(dict.fromkeys(profile["insights"] + ["Preference profile updated by owner"]))[-12:]
        profile["confidence"] = round(clamp(float(profile["confidence"]) + 0.04, 0.0, 0.96), 3)
        self._persist(profile)
        return profile

    def _persist(self, profile: dict[str, Any]) -> None:
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                UPDATE buying_intelligence_profiles
                SET preferences = ?, budget_patterns = ?, brand_preferences = ?,
                    purchase_history = ?, risk_tolerance = ?, insights = ?,
                    confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    dumps(profile["preferences"]),
                    dumps(profile["budget_patterns"]),
                    dumps(profile["brand_preferences"]),
                    dumps(profile["purchase_history"]),
                    dumps(profile["risk_tolerance"]),
                    dumps(profile["insights"]),
                    profile["confidence"],
                    utc_now(),
                    profile["id"],
                ),
            )

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("preferences", "budget_patterns", "brand_preferences", "purchase_history", "risk_tolerance", "insights"):
            data[key] = loads(data.get(key), [] if key in {"purchase_history", "insights"} else {})
        return data
