from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..agents.coordinator import Coordinator
from ..database.store import CognitiveStore, dumps, utc_now
from .reasoning import InputUnderstandingEngine


INTENT_AGENTS = {
    "artifact_generation": ["PlanningAgent", "FileAgent", "DataAgent", "QualityAgent", "TestingAgent"],
    "live_research": ["ResearchAgent", "AnalysisAgent", "QualityAgent"],
    "automation": ["PlanningAgent", "AutomationAgent", "BrowserAgent", "SecurityAgent", "QualityAgent"],
    "coding": ["PlanningAgent", "CodingAgent", "TestingAgent", "QualityAgent", "SecurityAgent"],
    "goal_management": ["PlanningAgent", "ResearchAgent", "MemoryAgent", "AnalysisAgent", "QualityAgent"],
    "conversation": ["MemoryAgent", "PlanningAgent"],
}


class CognitivePlanner:
    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.understanding = InputUnderstandingEngine()
        self.coordinator = Coordinator(store)

    def plan(self, task: str) -> dict[str, Any]:
        understood = self.understanding.understand(task)
        required_agents = INTENT_AGENTS.get(understood["intent"], ["PlanningAgent"])
        complexity = self.coordinator.complexity_score(
            task_steps=len(understood["steps"]),
            required_tools=max(1, len(understood["required_tools"])),
            estimated_runtime=max(1.0, len(task) / 120.0),
            uncertainty_score=0.5 + understood["task_complexity"] / 200.0,
            dependencies=max(1, len(required_agents) // 2),
        )
        plan_id = f"plan_{uuid4().hex}"
        created_at = utc_now()
        plan = {
            "plan_id": plan_id,
            "task": task,
            "understanding": understood,
            "complexity_score": complexity,
            "required_agents": required_agents,
            "risk_level": understood["risk_level"],
            "confidence": 0.74 if understood["risk_level"] == "low" else 0.62,
            "created_at": created_at,
        }
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO plans(id, task, decomposition, risk_level, required_agents, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    task,
                    dumps(understood["steps"]),
                    understood["risk_level"],
                    dumps(required_agents),
                    plan["confidence"],
                    created_at,
                ),
            )
        return plan
