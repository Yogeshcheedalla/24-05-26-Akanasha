from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now
from ..world.world_model import WorldModelEngine


class KnowledgeGraphEngine:
    """Stores explicit relationships while mirroring entities into the world model."""

    ENTITY_TYPES = {"relationship", "project", "dependency", "goal", "skill", "user", "document", "task"}
    WORLD_TYPE_MAP = {
        "dependency": "relationship",
        "skill": "preference",
        "document": "project",
        "task": "goal",
    }

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.world_model = WorldModelEngine(store)

    def upsert_entity(
        self,
        entity_type: str,
        name: str,
        attributes: dict[str, Any] | None = None,
        confidence: float = 0.75,
    ) -> dict[str, Any]:
        if entity_type not in self.ENTITY_TYPES:
            raise ValueError(f"Unsupported knowledge entity type: {entity_type}")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Knowledge entity name cannot be empty")
        now = utc_now()
        fingerprint = stable_fingerprint(f"knowledge:{entity_type}:{clean_name}")
        attributes = attributes or {}
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM knowledge_graph_facts WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE knowledge_graph_facts
                    SET attributes = ?, confidence = MAX(confidence, ?), updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (dumps({**loads(existing["attributes"], {}), **attributes}), self._clamp(confidence), now, fingerprint),
                )
                row = conn.execute("SELECT * FROM knowledge_graph_facts WHERE fingerprint = ?", (fingerprint,)).fetchone()
                decoded = self._decode_entity(row)
                decoded["deduplicated"] = True
            else:
                entity_id = f"kg_{uuid4().hex}"
                conn.execute(
                    """
                    INSERT INTO knowledge_graph_facts(
                        id, entity_type, name, attributes, confidence, fingerprint, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (entity_id, entity_type, clean_name, dumps(attributes), self._clamp(confidence), fingerprint, now, now),
                )
                row = conn.execute("SELECT * FROM knowledge_graph_facts WHERE id = ?", (entity_id,)).fetchone()
                decoded = self._decode_entity(row)
                decoded["deduplicated"] = False
        self.world_model.upsert_node(self._world_type(entity_type), clean_name, attributes, confidence)
        return decoded

    def link(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        attributes: dict[str, Any] | None = None,
        confidence: float = 0.75,
    ) -> dict[str, Any]:
        source = self._require_entity(source_id)
        target = self._require_entity(target_id)
        clean_relationship = relationship.strip()
        if not clean_relationship:
            raise ValueError("Knowledge relationship cannot be empty")
        now = utc_now()
        attributes = attributes or {}
        fingerprint = stable_fingerprint(f"kg-link:{source_id}:{clean_relationship}:{target_id}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM knowledge_graph_links WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE knowledge_graph_links SET attributes = ?, confidence = MAX(confidence, ?), updated_at = ? WHERE fingerprint = ?",
                    (dumps({**loads(existing["attributes"], {}), **attributes}), self._clamp(confidence), now, fingerprint),
                )
                row = conn.execute("SELECT * FROM knowledge_graph_links WHERE fingerprint = ?", (fingerprint,)).fetchone()
                decoded = self._decode_link(row)
                decoded["deduplicated"] = True
            else:
                link_id = f"kg_link_{uuid4().hex}"
                conn.execute(
                    """
                    INSERT INTO knowledge_graph_links(
                        id, source_id, target_id, relationship, attributes, confidence,
                        fingerprint, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (link_id, source_id, target_id, clean_relationship, dumps(attributes), self._clamp(confidence), fingerprint, now, now),
                )
                row = conn.execute("SELECT * FROM knowledge_graph_links WHERE id = ?", (link_id,)).fetchone()
                decoded = self._decode_link(row)
                decoded["deduplicated"] = False
        world_source = self.world_model.upsert_node(
            self._world_type(source["entity_type"]),
            source["name"],
            source["attributes"],
            source["confidence"],
        )
        world_target = self.world_model.upsert_node(
            self._world_type(target["entity_type"]),
            target["name"],
            target["attributes"],
            target["confidence"],
        )
        self.world_model.add_edge(world_source["id"], world_target["id"], clean_relationship, attributes, confidence)
        return decoded

    def graph(self, limit: int = 100) -> dict[str, Any]:
        bounded = max(1, min(limit, 500))
        with self.store.connect(self.store.files.agents) as conn:
            entities = [self._decode_entity(row) for row in conn.execute(
                "SELECT * FROM knowledge_graph_facts ORDER BY updated_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()]
            links = [self._decode_link(row) for row in conn.execute(
                "SELECT * FROM knowledge_graph_links ORDER BY updated_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()]
        return {
            "entities": entities,
            "links": links,
            "world_model_projection": self.world_model.graph(limit=bounded),
        }

    def ingest_goal_skill_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        created: list[dict[str, Any]] = []
        goal = payload.get("goal")
        user = payload.get("user")
        skills = payload.get("skills", [])
        if user:
            created.append(self.upsert_entity("user", str(user), {"source": "ingest"}, 0.82))
        if goal:
            created.append(self.upsert_entity("goal", str(goal), {"source": "ingest"}, 0.82))
        for skill in skills:
            created.append(self.upsert_entity("skill", str(skill), {"source": "ingest"}, 0.78))
        return {"created": created, "count": len(created)}

    def _require_entity(self, entity_id: str) -> dict[str, Any]:
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM knowledge_graph_facts WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown knowledge entity: {entity_id}")
        return self._decode_entity(row)

    def _decode_entity(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["attributes"] = loads(data.get("attributes"), {})
        return data

    def _decode_link(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["attributes"] = loads(data.get("attributes"), {})
        return data

    def _clamp(self, value: float) -> float:
        return round(max(0.0, min(1.0, float(value))), 3)

    def _world_type(self, entity_type: str) -> str:
        return entity_type if entity_type in WorldModelEngine.NODE_TYPES else self.WORLD_TYPE_MAP.get(entity_type, "project")
