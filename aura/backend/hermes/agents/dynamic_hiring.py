from __future__ import annotations

from typing import Any

from .agent_factory import AGENT_TYPES


class DynamicHiringEngine:
    """Computes bounded specialized-agent plans from task complexity."""

    def recommended_army_size(self, complexity_score: float) -> int:
        if complexity_score < 30:
            return 2
        if complexity_score < 60:
            return 5
        if complexity_score < 90:
            return 8
        return 10

    def recommended_temporary_workers(self, complexity_score: float) -> int:
        if complexity_score < 30:
            return 0
        if complexity_score < 60:
            return 2
        if complexity_score < 90:
            return 4
        return 6

    def select_agent_types(self, intent: str, tools: list[str], dependencies: list[str]) -> list[str]:
        selected = ["PlanningAgent", "QualityAgent"]
        selected.extend(agent for agent in dependencies if agent in AGENT_TYPES)
        if intent == "live_research":
            selected.extend(["ResearchAgent", "AnalysisAgent"])
        if intent == "goal_management":
            selected.extend(["PlanningAgent", "ResearchAgent", "MemoryAgent", "AnalysisAgent", "QualityAgent"])
        if intent == "commerce":
            selected.extend(["ShoppingAgent", "ResearchAgent", "AnalysisAgent", "SecurityAgent", "QualityAgent"])
        if intent == "booking":
            selected.extend(["BookingAgent", "PlanningAgent", "ResearchAgent", "SecurityAgent", "QualityAgent"])
        if intent == "life_automation":
            selected.extend(["AutomationAgent", "PlanningAgent", "MemoryAgent", "SecurityAgent", "QualityAgent"])
        if intent == "concierge":
            selected.extend(["ConciergeAgent", "PlanningAgent", "ResearchAgent", "AutomationAgent", "QualityAgent"])
        if intent == "education":
            selected.extend(["ResearchAgent", "CreativeAgent", "MemoryAgent", "QualityAgent"])
        if intent == "communication":
            selected.extend(["AutomationAgent", "SecurityAgent", "QualityAgent"])
        if intent == "data_processing":
            selected.extend(["DataAgent", "AnalysisAgent", "FileAgent", "QualityAgent"])
        if intent == "media":
            selected.extend(["CreativeAgent", "AnalysisAgent", "FileAgent", "QualityAgent"])
        if intent == "file_management":
            selected.extend(["FileAgent", "AutomationAgent", "SecurityAgent"])
        if intent == "api_workflow":
            selected.extend(["CodingAgent", "TestingAgent", "SecurityAgent", "DeploymentAgent"])
        if intent == "system_management":
            selected.extend(["AutomationAgent", "TestingAgent", "SecurityAgent", "QualityAgent"])
        if intent == "artifact_generation":
            selected.extend(["FileAgent", "DataAgent"])
        if intent == "coding":
            selected.extend(["CodingAgent", "TestingAgent", "SecurityAgent"])
        if "browser_automation" in tools:
            selected.extend(["BrowserAgent", "AutomationAgent", "SecurityAgent"])
        if "desktop_control" in tools:
            selected.extend(["AutomationAgent", "SecurityAgent"])
        return list(dict.fromkeys(selected))[:10]

    def hiring_plan(self, analysis: dict[str, Any]) -> dict[str, Any]:
        agent_types = self.select_agent_types(
            analysis["intent"],
            analysis["tools"],
            analysis["dependencies"],
        )
        return {
            "complexity_score": analysis["complexity_score"],
            "persistent_army_size": min(self.recommended_army_size(analysis["complexity_score"]), len(agent_types)),
            "temporary_worker_count": self.recommended_temporary_workers(analysis["complexity_score"]),
            "agent_types": agent_types,
            "policy": "bounded_no_recursive_spawning",
        }
