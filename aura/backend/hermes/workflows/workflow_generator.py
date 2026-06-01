from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..agents.dynamic_hiring import DynamicHiringEngine
from ..agents.task_analyzer import TaskAnalyzerAgent
from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class WorkflowGenerator:
    """Builds auditable workflow chains from user intent."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.analyzer = TaskAnalyzerAgent()
        self.hiring = DynamicHiringEngine()

    def generate(self, task: str) -> dict[str, Any]:
        analysis = self.analyzer.analyze(task).to_dict()
        hiring_plan = self.hiring.hiring_plan(analysis)
        steps = self._steps(task, analysis, hiring_plan)
        name = self._name(task, analysis["intent"])
        fingerprint = stable_fingerprint(f"{name}:{analysis['intent']}:{'|'.join(steps)}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM workflow_templates WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing, analysis, hiring_plan, deduplicated=True)
            workflow_id = f"workflow_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO workflow_templates(
                    id, name, intent, steps, required_tools, agent_types,
                    risk_level, confidence, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    name,
                    analysis["intent"],
                    dumps(steps),
                    dumps(analysis["tools"]),
                    dumps(hiring_plan["agent_types"]),
                    analysis["risk_level"],
                    self._confidence(analysis),
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM workflow_templates WHERE id = ?", (workflow_id,)).fetchone()
        return self._decode(row, analysis, hiring_plan) if row else {"id": workflow_id}

    def _steps(self, task: str, analysis: dict[str, Any], hiring_plan: dict[str, Any]) -> list[str]:
        steps = ["Understand user goal and constraints"]
        if analysis["intent"] == "live_research":
            steps.extend(["Fetch live sources", "Cross-check source timestamp", "Extract answer with citations"])
        elif analysis["intent"] == "artifact_generation":
            steps.extend(["Plan artifact structure", "Generate content", "Write file", "Verify file opens"])
        elif analysis["intent"] == "coding":
            steps.extend(["Inspect repository", "Patch scoped files", "Run targeted tests", "Summarize changes"])
        elif analysis["intent"] == "goal_management":
            steps.extend(
                [
                    "Analyze long-term goal and owner context",
                    "Create goal graph preview",
                    "Map dependencies, milestones, and priority",
                    "Route executive brain agents and skills",
                    "Prepare progress tracking and replay hooks",
                ]
            )
        elif analysis["intent"] == "commerce":
            steps.extend(
                [
                    "Extract budget, product constraints, and buying preferences",
                    "Plan multi-source product search through governed tool layer",
                    "Compare price, specs, reviews, delivery, history, and quality",
                    "Run verification and fraud/risk checks",
                    "Ask owner approval before purchase execution",
                    "Record buying intelligence and action metrics",
                ]
            )
        elif analysis["intent"] == "booking":
            steps.extend(
                [
                    "Extract booking type, schedule, budget, and constraints",
                    "Plan provider search and availability recheck",
                    "Compare price, reviews, cancellation policy, and schedule fit",
                    "Check duplicate bookings and calendar conflicts",
                    "Ask owner approval before confirmation or payment",
                    "Record booking outcome and action metrics",
                ]
            )
        elif analysis["intent"] == "life_automation":
            steps.extend(
                [
                    "Extract trigger, date, reminder title, and action scope",
                    "Validate schedule and notification permissions",
                    "Create bounded automation plan",
                    "Ask owner approval for external side effects",
                    "Track completion and learn phrase patterns",
                ]
            )
        elif analysis["intent"] == "concierge":
            steps.extend(
                [
                    "Classify concierge mode and user preferences",
                    "Generate itinerary or recommendation plan",
                    "Route maps, calendar, browser, and document services",
                    "Verify availability and conflicts",
                    "Ask owner approval before bookings or messages",
                ]
            )
        elif analysis["intent"] in {
            "education",
            "communication",
            "data_processing",
            "media",
            "file_management",
            "api_workflow",
            "system_management",
        }:
            steps.extend(
                [
                    "Classify universal task domain",
                    "Extract missing constraints and confidence blockers",
                    "Route through universal automation and tool layer",
                    "Generate verifiable intermediate outputs",
                    "Run validation and self-healing checks",
                    "Update memory, learning, and observatory dashboard",
                ]
            )
        elif analysis["intent"] == "automation":
            steps.extend(["Validate permission", "Plan desktop/browser action", "Execute only approved steps", "Confirm result"])
        else:
            steps.append("Answer conversationally with memory-aware context")
        if any(word in task.lower() for word in ["experiment", "a/b", "compare workflow", "compare prompt"]):
            steps.extend(["Create experiment variants", "Score variants", "Select winning workflow"])
        if any(word in task.lower() for word in ["test", "regression", "verify", "health check"]):
            steps.extend(["Generate autonomous test plan", "Record regression report", "Update observatory health"])
        if hiring_plan["temporary_worker_count"]:
            steps.append(f"Spawn {hiring_plan['temporary_worker_count']} isolated temporary workers")
        steps.extend(["Run validation agent", "Explain action selection", "Record replay event", "Record experience and lessons"])
        return steps

    def _name(self, task: str, intent: str) -> str:
        words = [word for word in task.replace("/", " ").split() if word.strip()]
        return f"{intent.title()} Workflow: {' '.join(words[:8])}"[:120]

    def _confidence(self, analysis: dict[str, Any]) -> float:
        uncertainty = float(analysis.get("uncertainty_score", 0.5))
        return round(max(0.45, min(0.92, 1.0 - (uncertainty * 0.45))), 3)

    def _decode(
        self,
        row: Any,
        analysis: dict[str, Any],
        hiring_plan: dict[str, Any],
        deduplicated: bool = False,
    ) -> dict[str, Any]:
        data = dict(row)
        data["steps"] = loads(data.get("steps"), [])
        data["required_tools"] = loads(data.get("required_tools"), [])
        data["agent_types"] = loads(data.get("agent_types"), [])
        data["analysis"] = analysis
        data["hiring_plan"] = hiring_plan
        data["deduplicated"] = deduplicated
        return data
