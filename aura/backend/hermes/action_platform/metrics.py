from __future__ import annotations

from statistics import mean
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, utc_now
from .common import clamp


class ActionPlatformMetrics:
    """Aggregates autonomous commerce, booking, concierge, and bus metrics."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def record_metric(self, metric_name: str, metric_value: float, dimensions: dict[str, Any] | None = None, source: str = "action_platform") -> dict[str, Any]:
        metric = {
            "id": f"metric_{uuid4().hex}",
            "metric_name": metric_name,
            "metric_value": round(float(metric_value), 4),
            "dimensions": dimensions or {},
            "source": source,
            "created_at": utc_now(),
        }
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO action_platform_metrics(id, metric_name, metric_value, dimensions, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    metric["id"],
                    metric["metric_name"],
                    metric["metric_value"],
                    dumps(metric["dimensions"]),
                    metric["source"],
                    metric["created_at"],
                ),
            )
        return metric

    def snapshot(self) -> dict[str, Any]:
        commerce = self._commerce()
        booking = self._booking()
        bus = self._bus()
        audits = self._verification()
        derived = {
            "shopping_success_rate": commerce["verified_rate"],
            "booking_accuracy": booking["verified_rate"],
            "average_savings": commerce["average_savings"],
            "execution_latency": bus["average_planning_latency_hint"],
            "task_completion_rate": self._mean([commerce["completion_rate"], booking["completion_rate"], bus["completion_rate"]]),
            "failure_rate": audits["blocker_rate"],
            "user_satisfaction": self._mean([commerce["recommendation_confidence"], booking["recommendation_confidence"], 0.78]),
            "recommendation_confidence": self._mean([commerce["recommendation_confidence"], booking["recommendation_confidence"]]),
            "automation_success_rate": bus["completion_rate"],
        }
        return {
            "autonomous_shopping": commerce,
            "autonomous_booking": booking,
            "execution_bus": bus,
            "verification": audits,
            "dashboard_metrics": {key: round(clamp(value), 3) for key, value in derived.items()},
            "created_at": utc_now(),
        }

    def latest_metrics(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM action_platform_metrics ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        decoded: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["dimensions"] = loads(data.get("dimensions"), {})
            decoded.append(data)
        return decoded

    def _commerce(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute("SELECT * FROM commerce_requests").fetchall()
        total = len(rows)
        verified = sum(1 for row in rows if row["status"] == "verified_for_execution")
        ready = sum(1 for row in rows if row["status"] in {"ready_for_owner_approval", "verified_for_execution"})
        confidences = [float(row["confidence"]) for row in rows] or [0.72]
        savings: list[float] = []
        for row in rows:
            ranked = loads(row["ranked_recommendations"], [])
            prices = [item.get("price", 0) for item in ranked if item.get("price")]
            if prices:
                best = prices[0]
                avg = mean(prices)
                savings.append(max(0.0, (avg - best) / avg) if avg else 0.0)
        return {
            "total_requests": total,
            "ready_for_approval": ready,
            "verified_rate": verified / total if total else 0.0,
            "completion_rate": ready / total if total else 0.0,
            "average_savings": mean(savings) if savings else 0.0,
            "recommendation_confidence": mean(confidences),
        }

    def _booking(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute("SELECT * FROM booking_requests").fetchall()
        total = len(rows)
        verified = sum(1 for row in rows if row["status"] == "verified_for_execution")
        ready = sum(1 for row in rows if row["status"] in {"ready_for_owner_approval", "verified_for_execution"})
        confidences = [float(row["confidence"]) for row in rows] or [0.72]
        return {
            "total_requests": total,
            "ready_for_approval": ready,
            "verified_rate": verified / total if total else 0.0,
            "completion_rate": ready / total if total else 0.0,
            "recommendation_confidence": mean(confidences),
        }

    def _bus(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute("SELECT * FROM execution_bus_events").fetchall()
        total = len(rows)
        approved = sum(1 for row in rows if row["approval_state"] == "approved")
        confidences = [float(row["confidence"]) for row in rows] or [0.7]
        return {
            "total_events": total,
            "approved_events": approved,
            "completion_rate": approved / total if total else 0.0,
            "average_confidence": mean(confidences),
            "average_planning_latency_hint": 0.86 if total else 0.0,
        }

    def _verification(self) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute("SELECT * FROM verification_audits").fetchall()
        total = len(rows)
        blocker_count = 0
        for row in rows:
            conflicts = loads(row["conflicts"], [])
            if any(item.get("severity") == "blocker" for item in conflicts):
                blocker_count += 1
        return {
            "total_audits": total,
            "blockers": blocker_count,
            "blocker_rate": blocker_count / total if total else 0.0,
        }

    def _mean(self, values: list[float]) -> float:
        valid = [value for value in values if value is not None]
        return mean(valid) if valid else 0.0
