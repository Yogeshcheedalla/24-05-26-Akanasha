from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from ..reasoning.reasoning import InputUnderstandingEngine


@dataclass(frozen=True)
class TaskAnalysis:
    task: str
    intent: str
    steps: list[str]
    tools: list[str]
    dependencies: list[str]
    uncertainty_score: float
    estimated_runtime: float
    risk_level: str
    priority: str
    complexity_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskAnalyzerAgent:
    """Turns natural language into a measurable execution profile."""

    def __init__(self) -> None:
        self.understanding = InputUnderstandingEngine()

    def analyze(self, task: str) -> TaskAnalysis:
        understood = self.understanding.understand(task)
        steps = understood["steps"]
        tools = understood["required_tools"]
        dependencies = self._dependencies(understood["intent"], tools)
        uncertainty = self._uncertainty(task, tools, understood["risk_level"])
        runtime = max(1.0, len(task) / 110.0 + len(steps) * 0.4 + len(tools) * 0.6)
        complexity = round(
            (len(steps) * 8)
            + (max(1, len(tools)) * 9)
            + (max(1, len(dependencies)) * 6)
            + (uncertainty * 30)
            + min(20.0, runtime),
            3,
        )
        if understood["intent"] == "conversation" and not tools and len(steps) <= 1:
            complexity = min(complexity, 25.0)
        return TaskAnalysis(
            task=task,
            intent=understood["intent"],
            steps=steps,
            tools=tools,
            dependencies=dependencies,
            uncertainty_score=uncertainty,
            estimated_runtime=round(runtime, 3),
            risk_level=understood["risk_level"],
            priority=understood["priority"],
            complexity_score=complexity,
        )

    def _dependencies(self, intent: str, tools: list[str]) -> list[str]:
        dependencies = ["CoordinatorAgent", "ValidationAgent"]
        if intent == "live_research":
            dependencies.extend(["ResearchAgent", "QualityAgent"])
        if intent == "goal_management":
            dependencies.extend(["PlanningAgent", "ResearchAgent", "MemoryAgent", "AnalysisAgent", "QualityAgent"])
        if intent == "commerce":
            dependencies.extend(["ShoppingAgent", "ResearchAgent", "AnalysisAgent", "SecurityAgent", "QualityAgent"])
        if intent == "booking":
            dependencies.extend(["BookingAgent", "PlanningAgent", "ResearchAgent", "SecurityAgent", "QualityAgent"])
        if intent == "life_automation":
            dependencies.extend(["AutomationAgent", "PlanningAgent", "MemoryAgent", "SecurityAgent"])
        if intent == "concierge":
            dependencies.extend(["ConciergeAgent", "PlanningAgent", "ResearchAgent", "AutomationAgent", "QualityAgent"])
        if intent == "education":
            dependencies.extend(["ResearchAgent", "CreativeAgent", "MemoryAgent", "QualityAgent"])
        if intent == "communication":
            dependencies.extend(["PlanningAgent", "AutomationAgent", "SecurityAgent", "QualityAgent"])
        if intent == "data_processing":
            dependencies.extend(["DataAgent", "AnalysisAgent", "FileAgent", "QualityAgent"])
        if intent == "media":
            dependencies.extend(["CreativeAgent", "AnalysisAgent", "FileAgent", "QualityAgent"])
        if intent == "file_management":
            dependencies.extend(["FileAgent", "AutomationAgent", "SecurityAgent"])
        if intent == "api_workflow":
            dependencies.extend(["CodingAgent", "TestingAgent", "SecurityAgent", "DeploymentAgent"])
        if intent == "system_management":
            dependencies.extend(["AutomationAgent", "TestingAgent", "SecurityAgent", "QualityAgent"])
        if intent == "artifact_generation":
            dependencies.extend(["FileAgent", "DataAgent", "QualityAgent"])
        if intent == "coding":
            dependencies.extend(["CodingAgent", "TestingAgent", "QualityAgent"])
        if "desktop_control" in tools or "browser_automation" in tools:
            dependencies.extend(["AutomationAgent", "SecurityAgent"])
        return list(dict.fromkeys(dependencies))

    def _uncertainty(self, task: str, tools: list[str], risk_level: str) -> float:
        uncertainty = 0.25
        if len(task) > 180:
            uncertainty += 0.15
        if len(tools) >= 3:
            uncertainty += 0.18
        if risk_level in {"high", "critical"}:
            uncertainty += 0.18
        if any(word in task.lower() for word in ["latest", "current", "live", "real-time"]):
            uncertainty += 0.12
        return round(min(0.95, uncertainty), 3)
