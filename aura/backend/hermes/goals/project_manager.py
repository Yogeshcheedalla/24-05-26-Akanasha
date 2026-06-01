from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..database.store import CognitiveStore, dumps, utc_now
from .goal_graph import GoalGraphEngine


class AutonomousProjectManager:
    """Turns goals into auditable execution plans and progress reports."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.graph = GoalGraphEngine(store)

    def create_execution_plan(self, goal_id: str) -> dict[str, Any]:
        details = self.graph.details(goal_id)
        if not details["tasks"]:
            details = self.graph.decompose_goal(goal_id)
            details = self.graph.details(goal_id)
        tasks = details["tasks"]
        blockers = self.detect_blockers(goal_id)
        execution_plan = {
            "goal_id": goal_id,
            "mode": "coordinator_managed_goal_execution",
            "task_count": len(tasks),
            "sequence": self._sequence(tasks),
            "agent_allocation": self._agent_allocation(tasks),
            "milestone_count": len(details["milestones"]),
            "blockers": blockers,
            "corrective_actions": self.recommend_corrective_actions(goal_id),
            "updated_at": utc_now(),
        }
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                "UPDATE goals SET execution_state = ?, updated_at = ? WHERE id = ?",
                (dumps(execution_plan), utc_now(), goal_id),
            )
        return execution_plan

    def update_task_status(self, task_id: str, status: str) -> dict[str, Any]:
        result = self.graph.update_task_status(task_id, status)
        result["execution_plan"] = self.create_execution_plan(result["goal_progress"]["goal_id"])
        return result

    def detect_blockers(self, goal_id: str) -> list[dict[str, Any]]:
        details = self.graph.details(goal_id)
        blockers: list[dict[str, Any]] = []
        task_by_id = {task["id"]: task for task in details["tasks"]}
        now = datetime.now(timezone.utc)
        for task in details["tasks"]:
            if task["status"] == "blocked":
                blockers.append(
                    {
                        "type": "blocked_task",
                        "task_id": task["id"],
                        "message": f"{task['title']} is explicitly blocked.",
                        "severity": "high",
                    }
                )
            for dep_id in task.get("dependency_ids", []):
                dep = task_by_id.get(dep_id)
                if dep and dep["status"] != "completed" and task["status"] in {"active", "completed"}:
                    blockers.append(
                        {
                            "type": "dependency_not_complete",
                            "task_id": task["id"],
                            "dependency_id": dep_id,
                            "message": f"{task['title']} depends on unfinished task {dep['title']}.",
                            "severity": "medium",
                        }
                    )
            if task.get("deadline"):
                try:
                    due = datetime.fromisoformat(task["deadline"].replace("Z", "+00:00"))
                    if due < now and task["status"] != "completed":
                        blockers.append(
                            {
                                "type": "overdue_task",
                                "task_id": task["id"],
                                "message": f"{task['title']} is overdue.",
                                "severity": "high",
                            }
                        )
                except ValueError:
                    blockers.append(
                        {
                            "type": "invalid_deadline",
                            "task_id": task["id"],
                            "message": f"{task['title']} has an invalid deadline.",
                            "severity": "medium",
                        }
                    )
        return blockers

    def progress_report(self, goal_id: str) -> dict[str, Any]:
        details = self.graph.details(goal_id)
        progress = details["progress"]
        return {
            "goal": details["goal"],
            "progress": progress,
            "active_tasks": [task for task in details["tasks"] if task["status"] == "active"],
            "next_tasks": [task for task in details["tasks"] if task["status"] == "pending"][:3],
            "completed_tasks": [task for task in details["tasks"] if task["status"] == "completed"],
            "blockers": self.detect_blockers(goal_id),
            "corrective_actions": self.recommend_corrective_actions(goal_id),
        }

    def recommend_corrective_actions(self, goal_id: str) -> list[str]:
        blockers = self.detect_blockers(goal_id)
        if not blockers:
            return [
                "Keep the next pending task small enough to finish in one focused session.",
                "Run validation after every milestone before expanding scope.",
            ]
        actions: list[str] = []
        if any(item["type"] == "blocked_task" for item in blockers):
            actions.append("Resolve blocked tasks first or split them into smaller unblocked tasks.")
        if any(item["type"] == "dependency_not_complete" for item in blockers):
            actions.append("Reorder execution so dependencies finish before dependent tasks start.")
        if any(item["type"] == "overdue_task" for item in blockers):
            actions.append("Re-estimate overdue work, reduce scope, or move the deadline with a risk note.")
        return actions

    def _sequence(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(tasks, key=lambda task: (-float(task["priority"]), task["created_at"]))
        return [
            {
                "task_id": task["id"],
                "title": task["title"],
                "agent_type": task["agent_type"],
                "skill_name": task["skill_name"],
                "status": task["status"],
                "dependency_ids": task.get("dependency_ids", []),
            }
            for task in ordered
        ]

    def _agent_allocation(self, tasks: list[dict[str, Any]]) -> dict[str, int]:
        allocation: dict[str, int] = {}
        for task in tasks:
            allocation[task["agent_type"]] = allocation.get(task["agent_type"], 0) + 1
        return allocation
