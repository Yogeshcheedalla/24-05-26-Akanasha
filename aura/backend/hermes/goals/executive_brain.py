from __future__ import annotations

import re
from typing import Any

from ..database.store import CognitiveStore
from .decision_simulation import DecisionSimulationEngine
from .goal_graph import GoalGraphEngine
from .opportunity_detection import OpportunityDetectionEngine
from .personal_os import PersonalOperatingSystem
from .project_manager import AutonomousProjectManager


class DigitalExecutiveBrain:
    """Goal-driven executive layer that coordinates existing Hermes systems."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.goal_graph = GoalGraphEngine(store)
        self.project_manager = AutonomousProjectManager(store)
        self.opportunities = OpportunityDetectionEngine(store)
        self.decisions = DecisionSimulationEngine(store)
        self.personal_os = PersonalOperatingSystem(store)

    def preview(self, task: str, analysis: dict[str, Any]) -> dict[str, Any]:
        goal_like = self._is_goal_like(task)
        suggested_flow = [
            "Goal Analyzer",
            "Goal Decomposition",
            "Dependency Mapping",
            "Priority Assignment",
            "Milestone Generation",
            "Goal Graph Storage",
            "Continuous Tracking",
            "Adaptive Optimization",
        ]
        return {
            "goal_like": goal_like,
            "recommended_mode": "autonomous_goal_engine" if goal_like else "standard_cognitive_routing",
            "reason": self._goal_reason(task) if goal_like else "Task does not request long-term goal tracking.",
            "suggested_flow": suggested_flow if goal_like else [],
            "safe_defaults": {
                "requires_user_confirmation_for_external_actions": True,
                "temporary_workers_cannot_spawn_workers": True,
                "durable_memory_written_only_by_coordinator": True,
            },
            "analysis_intent": analysis.get("intent"),
        }

    def intake_goal(
        self,
        title: str,
        goal_context: str = "",
        goal_type: str = "project",
        goal_owner: str = "Yogesh",
        priority: float = 0.75,
        deadline: str | None = None,
    ) -> dict[str, Any]:
        goal = self.goal_graph.create_goal(
            title=title,
            goal_context=goal_context,
            goal_type=goal_type,
            goal_owner=goal_owner,
            priority=priority,
            deadline=deadline,
            confidence=0.84,
        )
        decomposition = self.goal_graph.decompose_goal(goal["id"])
        execution_plan = self.project_manager.create_execution_plan(goal["id"])
        personal_item = self.personal_os.store_item(
            "goal",
            title=goal["title"],
            content=goal["goal_context"],
            attributes={"goal_id": goal["id"], "goal_type": goal["goal_type"]},
            confidence=0.84,
        )
        opportunity_scan = self.opportunities.detect(
            [
                {
                    "title": goal["title"],
                    "text": f"{goal['title']} {goal['goal_context']}",
                    "source": "goal_intake",
                    "confidence": 0.78,
                }
            ],
            goal_id=goal["id"],
        )
        return {
            "goal": self.goal_graph.get_goal(goal["id"]),
            "decomposition": decomposition,
            "execution_plan": execution_plan,
            "personal_os_item": personal_item,
            "opportunity_scan": opportunity_scan,
            "progress_report": self.project_manager.progress_report(goal["id"]),
            "executive_summary": self._summary(goal["title"], execution_plan),
        }

    def progress_report(self, goal_id: str) -> dict[str, Any]:
        return self.project_manager.progress_report(goal_id)

    def simulate_decision_for_goal(self, goal_id: str, decision: str, choices: list[str]) -> dict[str, Any]:
        details = self.goal_graph.details(goal_id)
        context = {
            "goal_id": goal_id,
            "goal_health": details["goal"]["goal_health"],
            "progress": details["goal"]["progress"],
            "resource_pressure": min(1.0, len(details["tasks"]) / 10.0),
        }
        return self.decisions.simulate(decision, choices, context)

    def _is_goal_like(self, task: str) -> bool:
        lowered = task.lower()
        return bool(
            re.search(r"\b(goal|build .* months|startup|project plan|milestone|deadline|roadmap|chief of staff)\b", lowered)
            or re.search(r"\bin \d+\s*(day|week|month|year)s?\b", lowered)
        )

    def _goal_reason(self, task: str) -> str:
        lowered = task.lower()
        if "startup" in lowered:
            return "The task describes a long-horizon business objective that needs milestones, agents, tracking, and learning."
        if re.search(r"\bin \d+\s*(day|week|month|year)s?\b", lowered):
            return "The task contains a timeline, so it should be tracked as a goal with progress and risk scoring."
        return "The task asks for goal-style planning or progress management."

    def _summary(self, title: str, execution_plan: dict[str, Any]) -> str:
        return (
            f"Goal '{title}' is now structured as {execution_plan['task_count']} tasks, "
            f"{execution_plan['milestone_count']} milestones, and "
            f"{len(execution_plan['agent_allocation'])} specialized agent lanes."
        )
