from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from .common import clamp, compact_keywords, extract_budget, extract_priority
from .verification import VerificationRecheckEngine


class DigitalConciergeEngine:
    """Plans travel, restaurant, event, gift, meeting, and schedule workflows."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.verifier = VerificationRecheckEngine(store)

    def plan(self, user_intent: str, approved: bool = False) -> dict[str, Any]:
        plan_id = f"concierge_{uuid4().hex}"
        concierge_type = self._detect_type(user_intent)
        requirements = {
            "keywords": compact_keywords(user_intent),
            "budget": extract_budget(user_intent),
            "priorities": extract_priority(user_intent),
        }
        itinerary = self._itinerary(concierge_type, user_intent)
        recommendations = self._recommendations(concierge_type, requirements)
        schedule = {"time_zone": "Asia/Calcutta", "policy": "confirm exact times before booking or calendar changes"}
        verification = self.verifier.verify(
            "booking" if concierge_type in {"travel", "restaurant", "event"} else "concierge_plan",
            plan_id,
            {"options": recommendations, "missing_required": False, "unverified_assumptions": ["External availability must be checked before final action"]},
            approved=approved,
            irreversible=concierge_type in {"travel", "restaurant", "event"},
        )
        result = {
            "id": plan_id,
            "type": "digital_concierge",
            "concierge_type": concierge_type,
            "user_intent": user_intent,
            "requirement_profile": requirements,
            "itinerary": itinerary,
            "recommendations": recommendations,
            "schedule": schedule,
            "verification": verification,
            "approval_state": "approved_after_recheck" if verification["allowed_to_execute"] else "requires_owner_approval",
            "confidence": round(clamp(0.62 + verification["confidence"] * 0.25), 3),
            "status": "ready_for_owner_review",
            "created_at": utc_now(),
        }
        self._store(result)
        return result

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM concierge_plans ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _detect_type(self, text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in ["trip", "travel", "flight", "hotel"]):
            return "travel"
        if any(word in lowered for word in ["restaurant", "dinner", "lunch"]):
            return "restaurant"
        if any(word in lowered for word in ["meeting", "coordinate", "availability"]):
            return "meeting_coordination"
        if any(word in lowered for word in ["gift", "present"]):
            return "gift"
        if any(word in lowered for word in ["event", "birthday", "party"]):
            return "event"
        return "daily_schedule"

    def _itinerary(self, concierge_type: str, user_intent: str) -> list[dict[str, Any]]:
        templates = {
            "travel": ["define destination and dates", "compare transport", "compare stays", "plan local schedule", "confirm bookings"],
            "restaurant": ["detect cuisine/location", "compare ratings and distance", "check table availability", "ask approval", "reserve"],
            "meeting_coordination": ["collect participants", "find free slots", "propose agenda", "send invite after approval"],
            "event": ["define theme and budget", "compare venues/vendors", "schedule tasks", "confirm payments only after approval"],
            "gift": ["extract recipient and occasion", "compare gift ideas", "rank by budget and delivery", "ask approval"],
            "daily_schedule": ["collect commitments", "rank priorities", "schedule focus blocks", "set reminders after approval"],
        }
        return [{"order": index + 1, "task": task, "source_intent": user_intent} for index, task in enumerate(templates[concierge_type])]

    def _recommendations(self, concierge_type: str, requirements: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "title": f"{concierge_type.replace('_', ' ').title()} plan",
                "fit_score": 0.78,
                "rationale": "Matches extracted priorities and waits for external source verification before action",
                "requirements": requirements,
            }
        ]

    def _store(self, result: dict[str, Any]) -> None:
        fingerprint = stable_fingerprint(f"concierge:{result['concierge_type']}:{result['user_intent']}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO concierge_plans(
                    id, concierge_type, user_intent, itinerary, recommendations,
                    schedule, verification, approval_state, confidence, status,
                    fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["id"],
                    result["concierge_type"],
                    result["user_intent"],
                    dumps(result["itinerary"]),
                    dumps(result["recommendations"]),
                    dumps(result["schedule"]),
                    dumps(result["verification"]),
                    result["approval_state"],
                    result["confidence"],
                    result["status"],
                    fingerprint,
                    result["created_at"],
                    now,
                ),
            )

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("itinerary", "recommendations", "schedule", "verification"):
            data[key] = loads(data.get(key), [] if key in {"itinerary", "recommendations"} else {})
        return data
