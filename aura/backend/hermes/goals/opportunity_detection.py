from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class OpportunityDetectionEngine:
    """Ranks opportunities and risks from project, market, news, and workflow signals."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def detect(self, signals: list[str | dict[str, Any]], goal_id: str | None = None) -> dict[str, Any]:
        stored: list[dict[str, Any]] = []
        for signal in signals:
            parsed = self._parse_signal(signal)
            opportunity = self._store(parsed, goal_id)
            stored.append(opportunity)
        ranked = sorted(stored, key=lambda item: (-item["priority"], -item["confidence"], item["risk_score"]))
        return {
            "goal_id": goal_id,
            "opportunities": ranked,
            "top_recommendation": ranked[0]["recommendation"] if ranked else "",
            "count": len(ranked),
        }

    def list_opportunities(self, goal_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM opportunities"
        filters: list[str] = []
        params: list[Any] = []
        if goal_id:
            filters.append("goal_id = ?")
            params.append(goal_id)
        if status:
            filters.append("status = ?")
            params.append(status)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY priority DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode(row) for row in rows]

    def _parse_signal(self, signal: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(signal, dict):
            text = str(signal.get("text") or signal.get("title") or signal.get("message") or "")
            source = str(signal.get("source") or "manual")
            confidence = float(signal.get("confidence", 0.72))
        else:
            text = signal
            source = "manual"
            confidence = 0.72
        clean = re.sub(r"\s+", " ", text.strip())
        lowered = clean.lower()
        if re.search(r"\b(deadline|late|overdue|delay|blocked|risk|failed|failure)\b", lowered):
            signal_type = "risk"
            recommendation = "Review blocker, reduce scope, and create a corrective action before continuing."
            priority = 0.88
            risk_score = 0.72
        elif re.search(r"\b(news|trend|competitor|market|launch|funding|growth)\b", lowered):
            signal_type = "market"
            recommendation = "Route this to ResearchAgent and AnalysisAgent for source-backed opportunity validation."
            priority = 0.78
            risk_score = 0.38
        elif re.search(r"\b(github|commit|repo|test|deploy|build)\b", lowered):
            signal_type = "project_activity"
            recommendation = "Inspect recent project activity and update the execution plan if implementation velocity changed."
            priority = 0.74
            risk_score = 0.42
        elif re.search(r"\b(always|usually|habit|prefer|every time)\b", lowered):
            signal_type = "behavior_pattern"
            recommendation = "Store the pattern in memory and let the planner pre-fill the likely next workflow."
            priority = 0.7
            risk_score = 0.22
        else:
            signal_type = "general"
            recommendation = "Classify this signal against active goals and ask for confirmation before acting."
            priority = 0.55
            risk_score = 0.25
        return {
            "source": source,
            "signal_type": signal_type,
            "title": clean[:120] or "Untitled signal",
            "recommendation": recommendation,
            "priority": priority,
            "risk_score": risk_score,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _store(self, parsed: dict[str, Any], goal_id: str | None) -> dict[str, Any]:
        fingerprint = stable_fingerprint(f"opportunity:{goal_id}:{parsed['signal_type']}:{parsed['title']}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM opportunities WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE opportunities
                    SET priority = MAX(priority, ?), confidence = MAX(confidence, ?), updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (parsed["priority"], parsed["confidence"], now, fingerprint),
                )
                row = conn.execute("SELECT * FROM opportunities WHERE fingerprint = ?", (fingerprint,)).fetchone()
                return self._decode(row)
            opp_id = f"opp_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO opportunities(
                    id, goal_id, source, signal_type, title, recommendation, priority,
                    risk_score, confidence, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    opp_id,
                    goal_id,
                    parsed["source"],
                    parsed["signal_type"],
                    parsed["title"],
                    parsed["recommendation"],
                    parsed["priority"],
                    parsed["risk_score"],
                    parsed["confidence"],
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        return self._decode(row)

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = loads(data.get("metadata"), {})
        return data
