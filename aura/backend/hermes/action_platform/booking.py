from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from .common import clamp, compact_keywords, extract_budget, extract_priority, sortable_score
from .verification import VerificationRecheckEngine


class AutonomousBookingEngine:
    """Plans booking workflows while preserving conflict and approval gates."""

    BOOKING_TYPES = {
        "flight": ["flight", "plane", "airport"],
        "hotel": ["hotel", "stay", "room", "resort"],
        "restaurant": ["restaurant", "dinner", "lunch", "table"],
        "event": ["event", "concert", "show"],
        "appointment": ["appointment", "doctor", "meeting", "slot"],
        "ticket": ["ticket", "movie", "train"],
        "transport": ["cab", "taxi", "bus", "transport", "ride"],
    }

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.verifier = VerificationRecheckEngine(store)

    def plan(
        self,
        user_intent: str,
        options: list[dict[str, Any]] | None = None,
        approved: bool = False,
    ) -> dict[str, Any]:
        request_id = f"booking_{uuid4().hex}"
        booking_type = self.detect_type(user_intent)
        requirements = self._requirements(user_intent, booking_type)
        normalized = [self._normalize_option(item) for item in (options or [])]
        ranked = self._rank(normalized, requirements)
        schedule_validation = self._schedule_validation(requirements, ranked)
        conflict_analysis = self._conflict_analysis(requirements, ranked)
        verification = self.verifier.verify(
            "booking",
            request_id,
            {
                "options": ranked,
                "missing_required": not bool(ranked),
                "schedule_conflicts": conflict_analysis["blocking_conflicts"],
                "unverified_assumptions": [] if ranked else ["No verified booking options were provided"],
            },
            approved=approved,
            irreversible=True,
        )
        status = "ready_for_owner_approval" if ranked else "source_search_required"
        if verification["allowed_to_execute"]:
            status = "verified_for_execution"
        result = {
            "id": request_id,
            "type": "autonomous_booking",
            "booking_type": booking_type,
            "user_intent": user_intent,
            "requirement_profile": requirements,
            "source_plan": self._source_plan(user_intent, booking_type, requirements),
            "options": normalized,
            "ranked_recommendations": ranked,
            "schedule_validation": schedule_validation,
            "conflict_analysis": conflict_analysis,
            "verification": verification,
            "approval_state": "approved_after_recheck" if verification["allowed_to_execute"] else "requires_owner_approval",
            "execution_state": {
                "booking_confirmed": False,
                "policy": "never_confirm_booking_without_explicit_owner_confirmation",
                "calendar_integration": "planned_after_approval",
            },
            "confidence": self._confidence(ranked, schedule_validation, verification),
            "status": status,
            "created_at": utc_now(),
        }
        self._store(result)
        return result

    def list_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM booking_requests ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def detect_type(self, user_intent: str) -> str:
        lowered = user_intent.lower()
        for booking_type, needles in self.BOOKING_TYPES.items():
            if any(needle in lowered for needle in needles):
                return booking_type
        return "appointment"

    def _requirements(self, user_intent: str, booking_type: str) -> dict[str, Any]:
        return {
            "booking_type": booking_type,
            "keywords": compact_keywords(user_intent),
            "budget": extract_budget(user_intent),
            "priorities": extract_priority(user_intent),
            "date_signals": re.findall(r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\b", user_intent.lower()),
            "must_compare": ["price", "availability", "schedule_fit", "cancellation_policy", "distance_or_duration", "review_score"],
            "approval_required_before_confirmation": True,
        }

    def _source_plan(self, user_intent: str, booking_type: str, requirements: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": "multi_service_booking_comparison",
            "queries": [
                f"{booking_type} availability {user_intent}",
                f"{booking_type} price comparison {user_intent}",
                f"{booking_type} cancellation policy reviews {user_intent}",
            ],
            "required_sources": ["official_provider", "availability_source", "review_or_policy_source"],
            "source_rules": ["recheck availability immediately before confirmation", "validate schedule conflicts", "never pay or confirm without approval"],
        }

    def _normalize_option(self, option: dict[str, Any]) -> dict[str, Any]:
        title = str(option.get("title") or option.get("name") or "Unnamed option")
        price = sortable_score(option, "price", 0.0)
        rating = sortable_score(option, "rating", 0.0)
        review_score = sortable_score(option, "review_score", rating / 5 if rating > 1 else rating)
        schedule_fit = sortable_score(option, "schedule_fit", 0.7)
        cancellation_score = sortable_score(option, "cancellation_score", 0.65)
        duration_minutes = sortable_score(option, "duration_minutes", 60.0)
        return {
            **option,
            "title": title,
            "price": price,
            "rating": rating,
            "review_score": clamp(review_score if review_score <= 1 else review_score / 100),
            "schedule_fit": clamp(schedule_fit if schedule_fit <= 1 else schedule_fit / 100),
            "cancellation_score": clamp(cancellation_score if cancellation_score <= 1 else cancellation_score / 100),
            "duration_minutes": duration_minutes,
            "availability": option.get("availability", option.get("available", True)),
            "sources": option.get("sources", []),
        }

    def _rank(self, options: list[dict[str, Any]], requirements: dict[str, Any]) -> list[dict[str, Any]]:
        if not options:
            return []
        prices = [item["price"] for item in options if item["price"] > 0]
        max_price = max(prices) if prices else 1.0
        budget_amount = requirements["budget"].get("amount")
        ranked: list[dict[str, Any]] = []
        for item in options:
            price_score = 1 - (item["price"] / max_price) if max_price else 0.5
            if budget_amount and item["price"] > budget_amount:
                price_score -= 0.25
            duration_score = 1 - min(item["duration_minutes"], 360) / 360
            score = (
                price_score * 0.25
                + item["review_score"] * 0.22
                + item["schedule_fit"] * 0.26
                + item["cancellation_score"] * 0.15
                + duration_score * 0.12
            )
            if item["availability"] is False:
                score -= 0.3
            ranked.append(
                {
                    **item,
                    "rank_score": round(clamp(score), 4),
                    "approval_note": "Owner approval required before booking confirmation",
                }
            )
        return sorted(ranked, key=lambda item: item["rank_score"], reverse=True)

    def _schedule_validation(self, requirements: dict[str, Any], ranked: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "date_signals": requirements["date_signals"],
            "options_checked": len(ranked),
            "needs_calendar_check": True,
            "status": "ready_for_calendar_conflict_check" if ranked else "waiting_for_options",
        }

    def _conflict_analysis(self, requirements: dict[str, Any], ranked: list[dict[str, Any]]) -> dict[str, Any]:
        conflicts = [
            {"option": item["title"], "reason": item.get("conflict_reason", "calendar conflict")}
            for item in ranked
            if item.get("conflicts")
        ]
        return {
            "blocking_conflicts": conflicts,
            "conflict_policy": "do_not_confirm_until_calendar_and_duplicates_are_clear",
            "confidence": 0.76 if ranked else 0.48,
        }

    def _confidence(self, ranked: list[dict[str, Any]], schedule_validation: dict[str, Any], verification: dict[str, Any]) -> float:
        return round(clamp(0.48 + min(len(ranked), 5) * 0.06 + verification["confidence"] * 0.28 + (0.08 if schedule_validation["date_signals"] else 0.0)), 3)

    def _store(self, result: dict[str, Any]) -> None:
        fingerprint = stable_fingerprint(f"booking:{result['booking_type']}:{result['user_intent']}:{result['status']}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO booking_requests(
                    id, booking_type, user_intent, requirement_profile, options,
                    ranked_recommendations, schedule_validation, conflict_analysis,
                    verification, approval_state, execution_state, confidence,
                    status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["id"],
                    result["booking_type"],
                    result["user_intent"],
                    dumps(result["requirement_profile"]),
                    dumps(result["options"]),
                    dumps(result["ranked_recommendations"]),
                    dumps(result["schedule_validation"]),
                    dumps(result["conflict_analysis"]),
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
        for key in ("requirement_profile", "options", "ranked_recommendations", "schedule_validation", "conflict_analysis", "verification", "execution_state"):
            data[key] = loads(data.get(key), [] if key in {"options", "ranked_recommendations"} else {})
        return data
