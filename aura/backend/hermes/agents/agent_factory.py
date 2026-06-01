from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, utc_now


AGENT_TYPES = {
    "ResearchAgent",
    "CodingAgent",
    "MemoryAgent",
    "BrowserAgent",
    "VoiceAgent",
    "TestingAgent",
    "SecurityAgent",
    "QualityAgent",
    "PlanningAgent",
    "AnalysisAgent",
    "CreativeAgent",
    "DeploymentAgent",
    "AutomationAgent",
    "DataAgent",
    "FileAgent",
    "ShoppingAgent",
    "BookingAgent",
    "ConciergeAgent",
}

PERSISTENT_CORE_AGENTS = [
    "ResearchAgent",
    "CodingAgent",
    "MemoryAgent",
    "SecurityAgent",
    "AutomationAgent",
    "TestingAgent",
    "PlanningAgent",
    "VoiceAgent",
    "QualityAgent",
]


class AgentFactory:
    MAX_AGENTS = 10

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def hire(
        self,
        agent_name: str,
        specialization: str,
        goals: list[str],
        tools: list[str],
        memory_scope: str = "task",
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        if specialization not in AGENT_TYPES:
            raise ValueError(f"Unsupported agent type: {specialization}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
            if existing:
                return dict(existing)
            active_count = conn.execute("SELECT COUNT(*) AS count FROM agents WHERE status = 'active'").fetchone()["count"]
            if active_count >= self.MAX_AGENTS:
                raise ValueError("Agent limit reached; retire inactive agents before hiring more")
            now = utc_now()
            agent_id = f"agent_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO agents(
                    id, agent_name, specialization, goals, tools, memory_scope,
                    communication_protocol, status, confidence, created_at, updated_at, last_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    agent_name,
                    specialization,
                    dumps(goals),
                    dumps(tools),
                    memory_scope,
                    dumps({"format": "{sender, receiver, task, status, result, confidence}", "max_depth": 1}),
                    max(0.0, min(1.0, confidence)),
                    now,
                    now,
                    now,
                ),
            )
        return self.get(agent_name) or {"id": agent_id, "agent_name": agent_name}

    def ensure_persistent_core(self) -> list[dict[str, Any]]:
        self._make_room_for_core_agents()
        agents: list[dict[str, Any]] = []
        for agent_type in PERSISTENT_CORE_AGENTS:
            agents.append(
                self.hire(
                    agent_name=f"Core:{agent_type}",
                    specialization=agent_type,
                    goals=[f"Persistent {agent_type} capability for Akansha cognitive core"],
                    tools=[],
                    memory_scope="shared_memory_bus",
                    confidence=0.9,
                )
            )
        return agents

    def _make_room_for_core_agents(self) -> None:
        with self.store.connect(self.store.files.agents) as conn:
            active_core = conn.execute(
                "SELECT COUNT(*) AS count FROM agents WHERE status = 'active' AND agent_name LIKE 'Core:%'"
            ).fetchone()["count"]
            missing_core_slots = max(0, len(PERSISTENT_CORE_AGENTS) - active_core)
            active_total = conn.execute("SELECT COUNT(*) AS count FROM agents WHERE status = 'active'").fetchone()["count"]
            if active_total + missing_core_slots <= self.MAX_AGENTS:
                return
            conn.execute(
                """
                UPDATE agents
                SET status = 'retired', updated_at = ?
                WHERE status = 'active' AND agent_name NOT LIKE 'Core:%'
                """,
                (utc_now(),),
            )

    def create_temporary_worker(
        self,
        worker_name: str,
        specialization: str,
        task: str,
        tools: list[str],
    ) -> dict[str, Any]:
        if specialization not in AGENT_TYPES:
            raise ValueError(f"Unsupported worker type: {specialization}")
        return {
            "id": f"tmp_{uuid4().hex}",
            "agent_name": worker_name,
            "specialization": specialization,
            "goals": [task],
            "tools": tools,
            "memory_scope": "isolated_temporary",
            "communication_protocol": {
                "reports_to": "CoordinatorAgent",
                "can_spawn_workers": False,
                "auto_destroy_after_completion": True,
            },
            "status": "temporary",
            "confidence": 0.78,
        }

    def get(self, agent_name: str) -> dict[str, Any] | None:
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM agents WHERE agent_name = ?", (agent_name,)).fetchone()
        return dict(row) if row else None

    def retire_inactive(self, inactive_after_iso: str) -> int:
        with self.store.connect(self.store.files.agents) as conn:
            cursor = conn.execute(
                """
                UPDATE agents
                SET status = 'retired', updated_at = ?
                WHERE status = 'active' AND last_active < ?
                """,
                (utc_now(), inactive_after_iso),
            )
            return cursor.rowcount
