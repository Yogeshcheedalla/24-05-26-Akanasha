from __future__ import annotations

import re
from typing import Any

from ..database.store import loads


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def decode_json_fields(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    data = dict(row)
    for field in fields:
        if field in data:
            data[field] = loads(data.get(field), [] if field.endswith("s") else {})
    return data


def extract_budget(text: str) -> dict[str, Any]:
    lowered = text.lower()
    currency = "USD" if "$" in text or "dollar" in lowered else "INR" if "₹" in text or "rs" in lowered or "rupee" in lowered else ""
    match = re.search(r"(?:under|below|less than|upto|up to|max(?:imum)?)\s*(?:rs\.?|₹|\$)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", lowered)
    if not match:
        match = re.search(r"(?:rs\.?|₹|\$)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", lowered)
    if not match:
        return {"amount": None, "currency": currency, "constraint": "unspecified"}
    return {
        "amount": float(match.group(1).replace(",", "")),
        "currency": currency or "INR",
        "constraint": "maximum",
    }


def extract_priority(text: str) -> list[str]:
    lowered = text.lower()
    priorities: list[str] = []
    signals = {
        "battery": "battery_life",
        "delivery": "fast_delivery",
        "review": "reviews",
        "rating": "ratings",
        "cheap": "lowest_price",
        "budget": "lowest_price",
        "quality": "quality",
        "warranty": "warranty",
        "return": "return_policy",
        "near": "nearby",
        "family": "family_friendly",
        "quiet": "quiet",
    }
    for needle, value in signals.items():
        if needle in lowered and value not in priorities:
            priorities.append(value)
    return priorities or ["balanced_value"]


def compact_keywords(text: str, limit: int = 10) -> list[str]:
    stop = {
        "the",
        "and",
        "with",
        "for",
        "from",
        "that",
        "this",
        "best",
        "buy",
        "book",
        "please",
        "create",
        "under",
        "below",
        "today",
        "tomorrow",
    }
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    result: list[str] = []
    for word in words:
        if len(word) < 3 or word in stop:
            continue
        if word not in result:
            result.append(word)
        if len(result) >= limit:
            break
    return result


def sortable_score(candidate: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(candidate.get(key, default))
    except (TypeError, ValueError):
        return default
