from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class PersonalOperatingSystem:
    """Central user knowledge layer for projects, tasks, ideas, meetings, and habits."""

    ITEM_TYPES = {
        "project",
        "document",
        "knowledge",
        "idea",
        "meeting",
        "task",
        "learning_history",
        "note",
        "habit",
        "goal",
        "preference",
        "relationship",
        "activity_log",
        "decision_history",
        "execution_history",
        "priority_pattern",
    }

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def classify_and_store(self, text: str, attributes: dict[str, Any] | None = None, confidence: float = 0.74) -> dict[str, Any]:
        item_type = self.classify(text)
        title = self._title(text)
        return self.store_item(item_type, title, text, attributes or {"source": "classification"}, confidence)

    def store_item(
        self,
        item_type: str,
        title: str,
        content: str,
        attributes: dict[str, Any] | None = None,
        confidence: float = 0.74,
    ) -> dict[str, Any]:
        if item_type not in self.ITEM_TYPES:
            raise ValueError(f"Unsupported personal OS item type: {item_type}")
        clean_title = re.sub(r"\s+", " ", title.strip())
        clean_content = re.sub(r"\s+", " ", content.strip())
        if not clean_title or not clean_content:
            raise ValueError("Personal OS item requires title and content")
        fingerprint = stable_fingerprint(f"personal-os:{item_type}:{clean_title}:{clean_content[:180]}")
        now = utc_now()
        attributes = attributes or {}
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM personal_os_items WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                merged = loads(existing["attributes"], {})
                merged.update(attributes)
                conn.execute(
                    """
                    UPDATE personal_os_items
                    SET attributes = ?, confidence = MAX(confidence, ?), updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (dumps(merged), self._clamp(confidence), now, fingerprint),
                )
                row = conn.execute("SELECT * FROM personal_os_items WHERE fingerprint = ?", (fingerprint,)).fetchone()
                data = self._decode(row)
                data["deduplicated"] = True
                return data
            item_id = f"pos_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO personal_os_items(
                    id, item_type, title, content, attributes, confidence,
                    fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    item_type,
                    clean_title,
                    clean_content,
                    dumps(attributes),
                    self._clamp(confidence),
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM personal_os_items WHERE id = ?", (item_id,)).fetchone()
        data = self._decode(row)
        data["deduplicated"] = False
        return data

    def list_items(self, item_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM personal_os_items"
        params: list[Any] = []
        if item_type:
            query += " WHERE item_type = ?"
            params.append(item_type)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode(row) for row in rows]

    def context_bundle(self, query: str, limit: int = 10) -> dict[str, Any]:
        tokens = set(re.findall(r"[a-zA-Z0-9_]+", query.lower()))
        items = self.list_items(limit=200)
        scored = []
        for item in items:
            content_tokens = set(re.findall(r"[a-zA-Z0-9_]+", f"{item['title']} {item['content']}".lower()))
            overlap = len(tokens & content_tokens)
            if overlap:
                scored.append((overlap, item))
        scored.sort(key=lambda pair: (-pair[0], -float(pair[1]["confidence"])))
        selected = [item for _, item in scored[: max(1, min(limit, 20))]]
        return {
            "query": query,
            "items": selected,
            "item_types": sorted({item["item_type"] for item in selected}),
            "summary": " | ".join(item["title"] for item in selected[:5]),
        }

    def classify(self, text: str) -> str:
        lowered = text.lower()
        if re.search(r"\b(project|projects|repo|build|app|platform|code|coding)\b", lowered):
            return "project"
        if re.search(r"\b(meeting|call|discussion)\b", lowered):
            return "meeting"
        if re.search(r"\b(task|todo|remind|deadline)\b", lowered):
            return "task"
        if re.search(r"\b(idea|maybe|opportunity)\b", lowered):
            return "idea"
        if re.search(r"\b(prefer|always|language|tone)\b", lowered):
            return "preference"
        if re.search(r"\b(mother|father|friend|professor|relationship)\b", lowered):
            return "relationship"
        if re.search(r"\b(decision|choose|option)\b", lowered):
            return "decision_history"
        if re.search(r"\b(learn|study|exam|course)\b", lowered):
            return "learning_history"
        return "note"

    def _title(self, text: str) -> str:
        words = re.findall(r"[A-Za-z0-9+#.]+", text)
        return " ".join(words[:10]) if words else "Untitled memory item"

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["attributes"] = loads(data.get("attributes"), {})
        return data

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
