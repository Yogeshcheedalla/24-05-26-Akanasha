from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from .buying_intelligence import PersonalBuyingIntelligence
from .common import clamp, compact_keywords, extract_budget, extract_priority, sortable_score
from .verification import VerificationRecheckEngine


class AutonomousCommerceEngine:
    """Plans shopping decisions with verification and approval gates."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.buying = PersonalBuyingIntelligence(store)
        self.verifier = VerificationRecheckEngine(store)

    def plan(
        self,
        user_intent: str,
        candidates: list[dict[str, Any]] | None = None,
        owner: str = "Yogesh",
        approved: bool = False,
    ) -> dict[str, Any]:
        request_id = f"commerce_{uuid4().hex}"
        requirements = self._requirements(user_intent)
        self.buying.learn_from_intent(user_intent, owner=owner)
        buying_bias = self.buying.recommend_bias(requirements, owner=owner)
        normalized = [self._normalize_candidate(item) for item in (candidates or [])]
        ranked = self._rank(normalized, requirements, buying_bias["bias"])
        source_plan = self._source_plan(user_intent, requirements)
        verification = self.verifier.verify(
            "purchase",
            request_id,
            {
                "candidates": ranked,
                "missing_required": not bool(ranked),
                "unverified_assumptions": [] if ranked else ["No source candidate payload was provided to compare"],
            },
            approved=approved,
            irreversible=True,
        )
        status = "ready_for_owner_approval" if ranked else "source_search_required"
        if verification["allowed_to_execute"]:
            status = "verified_for_execution"
        result = {
            "id": request_id,
            "type": "autonomous_commerce",
            "user_intent": user_intent,
            "requirement_profile": requirements,
            "source_plan": source_plan,
            "product_candidates": normalized,
            "ranked_recommendations": ranked,
            "buying_intelligence": buying_bias,
            "verification": verification,
            "approval_state": "approved_after_recheck" if verification["allowed_to_execute"] else "requires_owner_approval",
            "execution_state": {
                "purchase_executed": False,
                "policy": "never_purchase_without_explicit_owner_confirmation",
                "next_step": "collect_verified_sources" if not ranked else "ask_owner_to_confirm_recommended_choice",
            },
            "confidence": self._confidence(ranked, verification),
            "status": status,
            "created_at": utc_now(),
        }
        self._store(result)
        return result

    def list_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM commerce_requests ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _requirements(self, user_intent: str) -> dict[str, Any]:
        keywords = compact_keywords(user_intent)
        category = self._category(user_intent, keywords)
        return {
            "category": category,
            "keywords": keywords,
            "budget": extract_budget(user_intent),
            "priorities": extract_priority(user_intent),
            "must_compare": [
                "price",
                "specifications",
                "reviews",
                "delivery_time",
                "historical_price",
                "quality_score",
                "user_preferences",
            ],
            "approval_required_before_purchase": True,
        }

    def _category(self, text: str, keywords: list[str]) -> str:
        lowered = text.lower()
        categories = {
            "headphone": "audio",
            "earbud": "audio",
            "phone": "mobile",
            "laptop": "computer",
            "shoe": "fashion",
            "book": "education",
            "gift": "gift",
        }
        for needle, category in categories.items():
            if needle in lowered:
                return category
        return keywords[0] if keywords else "general_product"

    def _source_plan(self, user_intent: str, requirements: dict[str, Any]) -> dict[str, Any]:
        category = requirements["category"]
        return {
            "mode": "multi_source_verified_comparison",
            "queries": [
                f"{category} official product specs {user_intent}",
                f"{category} verified reviews {user_intent}",
                f"{category} price history delivery comparison {user_intent}",
            ],
            "required_sources": ["official_store_or_marketplace", "review_source", "price_history_source"],
            "source_rules": [
                "prefer current timestamped pages",
                "cross-check price and availability before approval",
                "do not invent unavailable product data",
            ],
        }

    def _normalize_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        name = str(candidate.get("name") or candidate.get("title") or "Unnamed product")
        price = sortable_score(candidate, "price", sortable_score(candidate, "current_price", 0.0))
        rating = sortable_score(candidate, "rating", 0.0)
        review_score = sortable_score(candidate, "review_score", rating / 5 if rating > 1 else rating)
        quality_score = sortable_score(candidate, "quality_score", 0.65)
        delivery_days = sortable_score(candidate, "delivery_days", 7.0)
        historical_delta = sortable_score(candidate, "historical_price_delta", 0.0)
        return {
            **candidate,
            "name": name,
            "price": price,
            "rating": rating,
            "review_score": clamp(review_score if review_score <= 1 else review_score / 100),
            "quality_score": clamp(quality_score if quality_score <= 1 else quality_score / 100),
            "delivery_days": delivery_days,
            "historical_price_delta": historical_delta,
            "availability": candidate.get("availability", candidate.get("available", True)),
            "sources": candidate.get("sources", []),
        }

    def _rank(self, candidates: list[dict[str, Any]], requirements: dict[str, Any], bias: dict[str, float]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        prices = [item["price"] for item in candidates if item["price"] > 0]
        max_price = max(prices) if prices else 1.0
        budget_amount = requirements["budget"].get("amount")
        ranked: list[dict[str, Any]] = []
        for item in candidates:
            price_score = 1.0 - (item["price"] / max_price) if max_price else 0.5
            if budget_amount and item["price"] > budget_amount:
                price_score -= 0.25
            delivery_score = 1.0 - min(item["delivery_days"], 14.0) / 14.0
            history_score = 0.6 + clamp(-item["historical_price_delta"], -0.25, 0.25)
            score = (
                price_score * bias["price_weight"]
                + item["quality_score"] * bias["quality_weight"]
                + item["review_score"] * bias["review_weight"]
                + delivery_score * bias["delivery_weight"]
                + history_score * bias["history_weight"]
            )
            ranked.append(
                {
                    **item,
                    "rank_score": round(clamp(score), 4),
                    "pros": self._pros(item, requirements),
                    "cons": self._cons(item, requirements),
                    "approval_note": "Owner approval required before purchase execution",
                }
            )
        return sorted(ranked, key=lambda item: item["rank_score"], reverse=True)

    def _pros(self, item: dict[str, Any], requirements: dict[str, Any]) -> list[str]:
        pros: list[str] = []
        if item["quality_score"] >= 0.78:
            pros.append("Strong quality score")
        if item["review_score"] >= 0.78:
            pros.append("Strong review signal")
        if item["delivery_days"] <= 3:
            pros.append("Fast delivery")
        budget = requirements["budget"].get("amount")
        if budget and item["price"] <= budget:
            pros.append("Within stated budget")
        return pros or ["Balanced fit for the extracted requirements"]

    def _cons(self, item: dict[str, Any], requirements: dict[str, Any]) -> list[str]:
        cons: list[str] = []
        if item["availability"] is False:
            cons.append("Availability needs recheck")
        budget = requirements["budget"].get("amount")
        if budget and item["price"] > budget:
            cons.append("Above stated budget")
        if not item.get("sources"):
            cons.append("Needs source citation before purchase")
        return cons

    def _confidence(self, ranked: list[dict[str, Any]], verification: dict[str, Any]) -> float:
        source_signal = 0.12 if ranked and all(item.get("sources") for item in ranked[:1]) else 0.0
        return round(clamp(0.5 + min(len(ranked), 5) * 0.06 + source_signal + verification["confidence"] * 0.25), 3)

    def _store(self, result: dict[str, Any]) -> None:
        fingerprint = stable_fingerprint(f"commerce:{result['user_intent']}:{result['status']}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO commerce_requests(
                    id, user_intent, requirement_profile, product_candidates,
                    ranked_recommendations, verification, approval_state,
                    execution_state, confidence, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["id"],
                    result["user_intent"],
                    dumps(result["requirement_profile"]),
                    dumps(result["product_candidates"]),
                    dumps(result["ranked_recommendations"]),
                    dumps(result["verification"]),
                    result["approval_state"],
                    dumps(result["execution_state"]),
                    result["confidence"],
                    result["status"],
                    fingerprint,
                    result["created_at"],
                    now,
                ),
            )

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("requirement_profile", "product_candidates", "ranked_recommendations", "verification", "execution_state"):
            data[key] = loads(data.get(key), [] if key in {"product_candidates", "ranked_recommendations"} else {})
        return data
