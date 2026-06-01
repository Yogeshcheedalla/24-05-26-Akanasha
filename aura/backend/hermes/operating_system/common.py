from __future__ import annotations

from typing import Any


TASK_DOMAIN_BY_INTENT = {
    "conversation": "personal",
    "live_research": "research",
    "coding": "development",
    "artifact_generation": "documents",
    "automation": "automation",
    "goal_management": "planning",
    "commerce": "business",
    "booking": "travel",
    "life_automation": "scheduling",
    "concierge": "personal",
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def task_domain(intent: str) -> str:
    return TASK_DOMAIN_BY_INTENT.get(intent, "analysis")


def approval_state(approved: bool, blocked: bool = False) -> str:
    if approved:
        return "approved"
    if blocked:
        return "waiting_for_owner_approval"
    return "plan_only"


def compact_dict(value: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if key in value}
