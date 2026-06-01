from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class CognitiveDigitalTwinEngine:
    """Builds Akansha's owner-specific model from existing memory, goals, and work signals.

    The twin is deliberately conservative: it learns bounded patterns, stores the
    evidence behind each pattern, and never performs actions by itself. Execution
    remains governed by the coordinator, safety layer, and approval checks.
    """

    SIGNAL_TYPES = {
        "habit",
        "preference",
        "goal",
        "project",
        "learning_pattern",
        "work_pattern",
        "decision_history",
        "execution_history",
        "productivity_pattern",
        "behavior_trend",
    }

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def observe_task(self, task: str, analysis: dict[str, Any] | None = None, owner: str = "Yogesh") -> dict[str, Any]:
        clean = self._clean(task)
        if not clean:
            raise ValueError("Digital twin observation requires non-empty task text")
        signals = self._extract_signals(clean, analysis or {})
        stored = [self.upsert_signal(owner, signal["signal_type"], signal["content"], signal["attributes"], signal["confidence"]) for signal in signals]
        profile = self.rebuild_profile(owner)
        return {
            "owner": owner,
            "observed_signals": stored,
            "profile": profile,
            "reason": "Updated the personal digital twin with current task, intent, risk, project, habit, and decision signals.",
        }

    def upsert_signal(
        self,
        owner: str,
        signal_type: str,
        content: str,
        attributes: dict[str, Any] | None = None,
        confidence: float = 0.72,
        source: str = "task_observation",
    ) -> dict[str, Any]:
        if signal_type not in self.SIGNAL_TYPES:
            raise ValueError(f"Unsupported digital twin signal type: {signal_type}")
        clean_owner = self._clean(owner) or "Yogesh"
        clean_content = self._clean(content)
        if not clean_content:
            raise ValueError("Digital twin signal content cannot be empty")
        attributes = attributes or {}
        fingerprint = stable_fingerprint(f"digital-twin:{clean_owner}:{signal_type}:{clean_content}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM digital_twin_signals WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                merged_attributes = loads(existing["attributes"], {})
                merged_attributes.update(attributes)
                conn.execute(
                    """
                    UPDATE digital_twin_signals
                    SET attributes = ?, usage_count = usage_count + 1,
                        confidence = MAX(confidence, ?), updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (dumps(merged_attributes), self._clamp(confidence), now, fingerprint),
                )
                row = conn.execute("SELECT * FROM digital_twin_signals WHERE fingerprint = ?", (fingerprint,)).fetchone()
                data = self._decode_signal(row)
                data["deduplicated"] = True
                return data
            signal_id = f"dt_signal_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO digital_twin_signals(
                    id, owner, signal_type, content, attributes, confidence,
                    source, usage_count, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    signal_id,
                    clean_owner,
                    signal_type,
                    clean_content,
                    dumps(attributes),
                    self._clamp(confidence),
                    source,
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM digital_twin_signals WHERE id = ?", (signal_id,)).fetchone()
        data = self._decode_signal(row)
        data["deduplicated"] = False
        return data

    def rebuild_profile(self, owner: str = "Yogesh") -> dict[str, Any]:
        clean_owner = self._clean(owner) or "Yogesh"
        signals = self.signals(owner=clean_owner, limit=300)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for signal in signals:
            grouped[signal["signal_type"]].append(signal)
        profile = {
            "habits": self._top_contents(grouped["habit"]),
            "preferences": self._top_contents(grouped["preference"]),
            "goals": self._top_contents(grouped["goal"]),
            "projects": self._top_contents(grouped["project"]),
            "learning_patterns": self._top_contents(grouped["learning_pattern"]),
            "work_patterns": self._top_contents(grouped["work_pattern"]),
            "decision_history": self._top_contents(grouped["decision_history"]),
            "execution_history": self._top_contents(grouped["execution_history"]),
            "productivity_patterns": self._top_contents(grouped["productivity_pattern"]),
            "behavior_trends": self._trend_summary(grouped),
        }
        model_summary = self._model_summary(profile)
        confidence = self._profile_confidence(signals)
        now = utc_now()
        fingerprint = stable_fingerprint(f"digital-twin-profile:{clean_owner}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM digital_twin_profiles WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE digital_twin_profiles
                    SET model_summary = ?, habits = ?, preferences = ?, goals = ?, projects = ?,
                        learning_patterns = ?, work_patterns = ?, decision_history = ?,
                        execution_history = ?, productivity_patterns = ?, behavior_trends = ?,
                        confidence = ?, updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (
                        model_summary,
                        dumps(profile["habits"]),
                        dumps(profile["preferences"]),
                        dumps(profile["goals"]),
                        dumps(profile["projects"]),
                        dumps(profile["learning_patterns"]),
                        dumps(profile["work_patterns"]),
                        dumps(profile["decision_history"]),
                        dumps(profile["execution_history"]),
                        dumps(profile["productivity_patterns"]),
                        dumps(profile["behavior_trends"]),
                        confidence,
                        now,
                        fingerprint,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO digital_twin_profiles(
                        id, owner, model_summary, habits, preferences, goals, projects,
                        learning_patterns, work_patterns, decision_history,
                        execution_history, productivity_patterns, behavior_trends,
                        confidence, fingerprint, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"dt_profile_{uuid4().hex}",
                        clean_owner,
                        model_summary,
                        dumps(profile["habits"]),
                        dumps(profile["preferences"]),
                        dumps(profile["goals"]),
                        dumps(profile["projects"]),
                        dumps(profile["learning_patterns"]),
                        dumps(profile["work_patterns"]),
                        dumps(profile["decision_history"]),
                        dumps(profile["execution_history"]),
                        dumps(profile["productivity_patterns"]),
                        dumps(profile["behavior_trends"]),
                        confidence,
                        fingerprint,
                        now,
                        now,
                    ),
                )
            row = conn.execute("SELECT * FROM digital_twin_profiles WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return self._decode_profile(row)

    def profile(self, owner: str = "Yogesh") -> dict[str, Any]:
        clean_owner = self._clean(owner) or "Yogesh"
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM digital_twin_profiles WHERE owner = ? ORDER BY updated_at DESC LIMIT 1", (clean_owner,)).fetchone()
        return self._decode_profile(row) if row else self.rebuild_profile(clean_owner)

    def signals(self, owner: str = "Yogesh", signal_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clean_owner = self._clean(owner) or "Yogesh"
        query = "SELECT * FROM digital_twin_signals WHERE owner = ?"
        params: list[Any] = [clean_owner]
        if signal_type:
            query += " AND signal_type = ?"
            params.append(signal_type)
        query += " ORDER BY confidence DESC, usage_count DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_signal(row) for row in rows]

    def _extract_signals(self, task: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        lowered = task.lower()
        signals: list[dict[str, Any]] = []
        intent = str(analysis.get("intent", "conversation"))
        risk = str(analysis.get("risk_level", "low"))
        complexity = float(analysis.get("complexity_score", 0.0) or 0.0)

        if re.search(r"\b(always|usually|prefer|preference|mostly|normally)\b", lowered):
            signals.append(self._signal("preference", task, {"intent": intent, "risk": risk}, 0.83))
        if re.search(r"\b(delay|late|postpone|forget|repeat|again|stuck)\b", lowered):
            signals.append(self._signal("habit", task, {"pattern": "recurring friction", "intent": intent}, 0.8))
        if re.search(r"\b(test|testing|debug|fix|verify|recheck)\b", lowered):
            signals.append(self._signal("work_pattern", "Validation and testing matter strongly for this user.", {"source_task": task}, 0.82))
            signals.append(self._signal("productivity_pattern", "User prefers recheck-and-verify loops before completion.", {"source_task": task}, 0.8))
        if re.search(r"\b(startup|goal|milestone|roadmap|launch|build .+ months?)\b", lowered):
            signals.append(self._signal("goal", task, {"intent": intent, "complexity": complexity}, 0.84))
        if re.search(r"\b(akansha|hermes|repo|project|app|platform|voice assistant)\b", lowered):
            signals.append(self._signal("project", task, {"intent": intent, "complexity": complexity}, 0.82))
        if re.search(r"\b(study|exam|learn|course|placement|interview)\b", lowered):
            signals.append(self._signal("learning_pattern", task, {"intent": intent}, 0.78))
        if re.search(r"\b(option|choice|decide|compare|buy|select)\b", lowered):
            signals.append(self._signal("decision_history", task, {"needs_comparison": True, "intent": intent}, 0.79))
        if intent in {"commerce", "booking", "life_automation", "coding", "document_generation", "live_research"}:
            signals.append(self._signal("execution_history", task, {"intent": intent, "risk": risk}, 0.77))
        if re.search(r"\b(tomorrow|today|deadline|schedule|week|month|time)\b", lowered):
            signals.append(self._signal("behavior_trend", task, {"time_sensitive": True, "intent": intent}, 0.76))

        if not signals:
            signals.append(self._signal("behavior_trend", task, {"intent": intent, "risk": risk}, 0.66))
        return signals

    def _signal(self, signal_type: str, content: str, attributes: dict[str, Any], confidence: float) -> dict[str, Any]:
        return {"signal_type": signal_type, "content": self._clean(content), "attributes": attributes, "confidence": confidence}

    def _top_contents(self, signals: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        return [
            {
                "content": signal["content"],
                "confidence": signal["confidence"],
                "usage_count": signal["usage_count"],
                "attributes": signal["attributes"],
            }
            for signal in signals[:limit]
        ]

    def _trend_summary(self, grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        trends: list[dict[str, Any]] = []
        if grouped["productivity_pattern"]:
            trends.append({"trend": "verification_first_user", "evidence_count": len(grouped["productivity_pattern"]), "confidence": 0.82})
        if grouped["work_pattern"]:
            trends.append({"trend": "engineering_and_quality_focus", "evidence_count": len(grouped["work_pattern"]), "confidence": 0.8})
        if grouped["behavior_trend"]:
            trends.append({"trend": "time_sensitive_planning_needed", "evidence_count": len(grouped["behavior_trend"]), "confidence": 0.76})
        if grouped["decision_history"]:
            trends.append({"trend": "prefers_comparison_before_action", "evidence_count": len(grouped["decision_history"]), "confidence": 0.78})
        return trends

    def _model_summary(self, profile: dict[str, Any]) -> str:
        parts = []
        if profile["projects"]:
            parts.append("active project context is strong")
        if profile["productivity_patterns"]:
            parts.append("verification loops are important")
        if profile["decision_history"]:
            parts.append("decisions should compare options and long-term value")
        if profile["behavior_trends"]:
            parts.append("time and deadline risk should be predicted early")
        return "; ".join(parts) if parts else "early-stage digital twin with limited but usable behavioral signals"

    def _profile_confidence(self, signals: list[dict[str, Any]]) -> float:
        if not signals:
            return 0.55
        avg = sum(float(signal["confidence"]) for signal in signals) / len(signals)
        coverage = min(0.18, len({signal["signal_type"] for signal in signals}) * 0.025)
        return round(self._clamp(avg + coverage), 4)

    def _decode_signal(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["attributes"] = loads(data.get("attributes"), {})
        return data

    def _decode_profile(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in (
            "habits",
            "preferences",
            "goals",
            "projects",
            "learning_patterns",
            "work_patterns",
            "decision_history",
            "execution_history",
            "productivity_patterns",
            "behavior_trends",
        ):
            data[key] = loads(data.get(key), [])
        return data

    def _clean(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
