from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, utc_now


class TimeMachineReplayEngine:
    """Records and reconstructs cognitive events without re-executing tools."""

    VALID_TYPES = {"task", "failure", "workflow", "learning", "experiment", "test"}

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def record(self, replay_type: str, reference_id: str, payload: dict[str, Any], confidence: float = 0.75) -> dict[str, Any]:
        if replay_type not in self.VALID_TYPES:
            raise ValueError(f"Unsupported replay type: {replay_type}")
        event_id = f"replay_{uuid4().hex}"
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO replay_events(id, replay_type, reference_id, payload, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, replay_type, reference_id, dumps(payload), max(0.0, min(1.0, confidence)), now),
            )
            row = conn.execute("SELECT * FROM replay_events WHERE id = ?", (event_id,)).fetchone()
        return self._decode(row)

    def replay(
        self,
        replay_type: str | None = None,
        reference_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        sql = "SELECT * FROM replay_events"
        clauses: list[str] = []
        params: list[Any] = []
        if replay_type:
            clauses.append("replay_type = ?")
            params.append(replay_type)
        if reference_id:
            clauses.append("reference_id = ?")
            params.append(reference_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC LIMIT ?"
        params.append(max(1, min(limit, 100)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        timeline = [self._decode(row) for row in rows]
        return {
            "timeline": timeline,
            "summary": self._summary(timeline),
            "count": len(timeline),
        }

    def replay_task(self, task: str, limit: int = 20) -> dict[str, Any]:
        with self.store.connect(self.store.files.experiences) as conn:
            experiences = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM experiences WHERE task LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f"%{task[:80]}%", max(1, min(limit, 50))),
                ).fetchall()
            ]
        events = self.replay("task", None, limit)["timeline"]
        matched = [event for event in events if task.lower()[:40] in dumps(event.get("payload", {})).lower()]
        return {"task": task, "experiences": experiences, "timeline": matched[:limit]}

    def _summary(self, timeline: list[dict[str, Any]]) -> dict[str, Any]:
        types: dict[str, int] = {}
        for event in timeline:
            types[event["replay_type"]] = types.get(event["replay_type"], 0) + 1
        avg_confidence = sum(float(event["confidence"]) for event in timeline) / len(timeline) if timeline else 0
        return {
            "types": types,
            "average_confidence": round(avg_confidence, 3),
            "first_event": timeline[0]["created_at"] if timeline else None,
            "last_event": timeline[-1]["created_at"] if timeline else None,
        }

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = loads(data.get("payload"), {})
        return data

