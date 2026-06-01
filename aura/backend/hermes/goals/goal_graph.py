from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


STATUS_WEIGHTS = {
    "pending": 0.0,
    "active": 0.2,
    "blocked": 0.15,
    "paused": 0.15,
    "completed": 1.0,
    "cancelled": 0.0,
}


class GoalGraphEngine:
    """Durable goal graph with hierarchy, dependencies, milestones, and progress.

    The graph is intentionally deterministic. It does not spawn agents or mutate
    unrelated memory. It stores the executive plan that other Hermes modules can
    read, validate, and execute safely.
    """

    GOAL_STATUSES = {"active", "blocked", "completed", "paused", "cancelled"}
    TASK_STATUSES = {"pending", "active", "blocked", "completed", "paused", "cancelled"}

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def create_goal(
        self,
        title: str,
        goal_context: str = "",
        goal_type: str = "project",
        goal_owner: str = "Yogesh",
        priority: float = 0.75,
        deadline: str | None = None,
        confidence: float = 0.78,
    ) -> dict[str, Any]:
        title = self._clean(title)
        if not title:
            raise ValueError("Goal title cannot be empty")
        self._validate_deadline(deadline)
        now = utc_now()
        fingerprint = stable_fingerprint(f"goal:{goal_owner}:{title}")
        context = self._clean(goal_context) or title
        existing_goal_id: str | None = None
        created_goal_id: str | None = None
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM goals WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                existing_goal_id = existing["id"]
                merged_context = self._merge_text(existing["goal_context"], context)
                conn.execute(
                    """
                    UPDATE goals
                    SET goal_context = ?, priority = MAX(priority, ?), deadline = COALESCE(?, deadline),
                        confidence = MAX(confidence, ?), updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (
                        merged_context,
                        self._clamp(priority),
                        deadline,
                        self._clamp(confidence),
                        now,
                        fingerprint,
                    ),
                )
            else:
                created_goal_id = f"goal_{uuid4().hex}"
                conn.execute(
                    """
                    INSERT INTO goals(
                        id, title, goal_type, goal_owner, goal_context, priority, deadline,
                        progress, status, estimated_effort, completion_score, goal_health,
                        blocked_reason, risk_score, milestones, execution_state, confidence,
                        fingerprint, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, 0, 'healthy', '', ?, '[]', '{}', ?, ?, ?, ?)
                    """,
                    (
                        created_goal_id,
                        title,
                        goal_type.strip() or "project",
                        goal_owner.strip() or "Yogesh",
                        context,
                        self._clamp(priority),
                        deadline,
                        self._estimate_effort(title, context),
                        self._risk_score(title, context, deadline),
                        self._clamp(confidence),
                        fingerprint,
                        now,
                        now,
                    ),
                )
        if existing_goal_id:
            self._record_event(existing_goal_id, "goal_deduplicated", {"title": title}, 0.9)
            goal = self.get_goal(existing_goal_id) or {"id": existing_goal_id}
            goal["deduplicated"] = True
            return goal
        assert created_goal_id is not None
        self._record_event(created_goal_id, "goal_created", {"title": title, "deadline": deadline}, confidence)
        goal = self.get_goal(created_goal_id) or {"id": created_goal_id}
        goal["deduplicated"] = False
        return goal

    def decompose_goal(self, goal_id: str) -> dict[str, Any]:
        goal = self._require_goal(goal_id)
        template = self._template_for(goal)
        created_tasks: list[dict[str, Any]] = []
        created_milestones: list[dict[str, Any]] = []
        previous_task_id: str | None = None
        for index, item in enumerate(template, start=1):
            task = self._upsert_task(
                goal_id=goal_id,
                title=item["title"],
                description=item["description"],
                agent_type=item["agent_type"],
                skill_name=item["skill_name"],
                priority=max(0.1, min(1.0, 1.0 - (index - 1) * 0.08)),
                estimated_effort=item["effort"],
                dependency_ids=[previous_task_id] if previous_task_id else [],
            )
            previous_task_id = task["id"]
            created_tasks.append(task)
            milestone = self._upsert_milestone(
                goal_id=goal_id,
                title=f"Milestone {index}: {item['title']}",
                due_at=self._distributed_due_date(goal.get("deadline"), index, len(template)),
                confidence=item["confidence"],
            )
            created_milestones.append(milestone)
        milestone_summary = [{"id": item["id"], "title": item["title"], "due_at": item["due_at"]} for item in created_milestones]
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                "UPDATE goals SET milestones = ?, updated_at = ? WHERE id = ?",
                (dumps(milestone_summary), utc_now(), goal_id),
            )
        self._record_event(goal_id, "goal_decomposed", {"tasks": len(created_tasks), "milestones": len(created_milestones)}, 0.86)
        return {
            "goal": self.get_goal(goal_id),
            "tasks": created_tasks,
            "milestones": created_milestones,
            "progress": self.calculate_progress(goal_id),
        }

    def add_dependency(
        self,
        goal_id: str,
        depends_on_goal_id: str,
        dependency_type: str = "blocks_until_complete",
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        self._require_goal(goal_id)
        self._require_goal(depends_on_goal_id)
        if goal_id == depends_on_goal_id:
            raise ValueError("A goal cannot depend on itself")
        if self._path_exists(depends_on_goal_id, goal_id):
            raise ValueError("Circular goal dependency prevented")
        dep_id = f"dep_{uuid4().hex}"
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute(
                "SELECT * FROM goal_dependencies WHERE goal_id = ? AND depends_on_goal_id = ?",
                (goal_id, depends_on_goal_id),
            ).fetchone()
            if existing:
                return self._decode_dependency(existing)
            conn.execute(
                """
                INSERT INTO goal_dependencies(id, goal_id, depends_on_goal_id, dependency_type, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (dep_id, goal_id, depends_on_goal_id, dependency_type, self._clamp(confidence), now),
            )
        self._record_event(goal_id, "dependency_added", {"depends_on_goal_id": depends_on_goal_id}, confidence)
        return self.get_dependency(dep_id) or {"id": dep_id}

    def update_goal_status(self, goal_id: str, status: str, blocked_reason: str = "") -> dict[str, Any]:
        if status not in self.GOAL_STATUSES:
            raise ValueError(f"Unsupported goal status: {status}")
        self._require_goal(goal_id)
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                UPDATE goals
                SET status = ?, blocked_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, blocked_reason if status == "blocked" else "", utc_now(), goal_id),
            )
        self._record_event(goal_id, "goal_status_updated", {"status": status, "blocked_reason": blocked_reason}, 0.82)
        return self.details(goal_id)

    def update_task_status(self, task_id: str, status: str) -> dict[str, Any]:
        if status not in self.TASK_STATUSES:
            raise ValueError(f"Unsupported task status: {status}")
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM goal_tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown task: {task_id}")
            conn.execute(
                "UPDATE goal_tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), task_id),
            )
            goal_id = row["goal_id"]
        progress = self.calculate_progress(goal_id)
        self._record_event(goal_id, "task_status_updated", {"task_id": task_id, "status": status}, 0.8)
        return {"task_id": task_id, "status": status, "goal_progress": progress}

    def calculate_progress(self, goal_id: str) -> dict[str, Any]:
        goal = self._require_goal(goal_id)
        with self.store.connect(self.store.files.agents) as conn:
            tasks = conn.execute("SELECT * FROM goal_tasks WHERE goal_id = ?", (goal_id,)).fetchall()
            milestones = conn.execute("SELECT * FROM goal_milestones WHERE goal_id = ?", (goal_id,)).fetchall()
        task_score = self._average([STATUS_WEIGHTS.get(row["status"], 0.0) for row in tasks])
        milestone_score = self._average([STATUS_WEIGHTS.get(row["status"], 0.0) for row in milestones])
        progress = round((task_score * 0.7 + milestone_score * 0.3) * 100, 2)
        completion_score = round(progress / 100, 4)
        blocked_tasks = [row["title"] for row in tasks if row["status"] == "blocked"]
        health = self._health(goal, progress, blocked_tasks)
        blocked_reason = "; ".join(blocked_tasks[:3]) if blocked_tasks else ""
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                UPDATE goals
                SET progress = ?, completion_score = ?, goal_health = ?, blocked_reason = ?,
                    status = CASE WHEN ? >= 100 THEN 'completed' ELSE status END,
                    updated_at = ?
                WHERE id = ?
                """,
                (progress, completion_score, health, blocked_reason, progress, utc_now(), goal_id),
            )
        return {
            "goal_id": goal_id,
            "progress": progress,
            "completion_score": completion_score,
            "goal_health": health,
            "blocked_reason": blocked_reason,
            "task_count": len(tasks),
            "milestone_count": len(milestones),
        }

    def details(self, goal_id: str) -> dict[str, Any]:
        goal = self._require_goal(goal_id)
        with self.store.connect(self.store.files.agents) as conn:
            tasks = conn.execute("SELECT * FROM goal_tasks WHERE goal_id = ? ORDER BY priority DESC, created_at ASC", (goal_id,)).fetchall()
            milestones = conn.execute("SELECT * FROM goal_milestones WHERE goal_id = ? ORDER BY created_at ASC", (goal_id,)).fetchall()
            dependencies = conn.execute("SELECT * FROM goal_dependencies WHERE goal_id = ?", (goal_id,)).fetchall()
            events = conn.execute("SELECT * FROM goal_events WHERE goal_id = ? ORDER BY created_at DESC LIMIT 20", (goal_id,)).fetchall()
        return {
            "goal": goal,
            "tasks": [self._decode_task(row) for row in tasks],
            "milestones": [self._decode_milestone(row) for row in milestones],
            "dependencies": [self._decode_dependency(row) for row in dependencies],
            "events": [self._decode_event(row) for row in events],
            "progress": self.calculate_progress(goal_id),
        }

    def list_goals(self, owner: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM goals"
        params: list[Any] = []
        filters: list[str] = []
        if owner:
            filters.append("goal_owner = ?")
            params.append(owner)
        if status:
            filters.append("status = ?")
            params.append(status)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY priority DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_goal(row) for row in rows]

    def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return self._decode_goal(row) if row else None

    def get_dependency(self, dependency_id: str) -> dict[str, Any] | None:
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM goal_dependencies WHERE id = ?", (dependency_id,)).fetchone()
        return self._decode_dependency(row) if row else None

    def _template_for(self, goal: dict[str, Any]) -> list[dict[str, Any]]:
        text = f"{goal['title']} {goal['goal_context']}".lower()
        if re.search(r"\bstartup|business|company|market|revenue|customer\b", text):
            phases = [
                ("Market research and positioning", "Research customers, competitors, pricing, and current market signals.", "ResearchAgent", "DeepResearchSkill", 4.0),
                ("Offer and product strategy", "Define ICP, value proposition, MVP boundary, and differentiation.", "PlanningAgent", "TaskPlanningSkill", 3.0),
                ("MVP build plan", "Break product into engineering, data, UX, and launch tasks.", "CodingAgent", "AutonomousDebugSkill", 5.0),
                ("Go-to-market workflow", "Create content, outreach, landing page, analytics, and feedback loop.", "CreativeAgent", "PresentationBuilderSkill", 3.5),
                ("Quality and risk validation", "Validate legal, security, reliability, and customer risks before launch.", "QualityAgent", "CodeReviewSkill", 2.5),
                ("Launch and learning loop", "Launch, measure metrics, extract lessons, and adapt the plan.", "AnalysisAgent", "WorkflowOptimizerSkill", 3.0),
            ]
        elif re.search(r"\bapp|website|platform|software|repo|github|deploy\b", text):
            phases = [
                ("Requirements and user flows", "Capture exact workflows, constraints, acceptance criteria, and UX states.", "PlanningAgent", "TaskPlanningSkill", 2.5),
                ("Architecture and data model", "Design APIs, schemas, services, queues, and safety boundaries.", "CodingAgent", "AutonomousDebugSkill", 4.0),
                ("Frontend implementation", "Build UI surfaces, states, generated outputs, and accessibility checks.", "CodingAgent", "CodeReviewSkill", 4.0),
                ("Backend implementation", "Implement services, persistence, validation, and observability.", "CodingAgent", "AutonomousDebugSkill", 4.5),
                ("Testing and quality gates", "Run unit, integration, security, and performance verification.", "TestingAgent", "BugDetectionSkill", 2.5),
                ("Deployment and monitoring", "Prepare release, environment checks, rollback, and monitoring.", "DeploymentAgent", "GitDeploySkill", 2.5),
            ]
        elif re.search(r"\bstudy|exam|learn|course|interview|placement\b", text):
            phases = [
                ("Baseline assessment", "Identify syllabus, weak topics, time remaining, and scoring goals.", "PlanningAgent", "TaskPlanningSkill", 1.5),
                ("Study plan", "Create topic sequence, daily slots, revision cycles, and practice checkpoints.", "PlanningAgent", "WorkflowOptimizerSkill", 2.0),
                ("Learning material generation", "Generate notes, examples, flashcards, questions, and formula sheets.", "CreativeAgent", "PDFGenerationSkill", 3.0),
                ("Practice and evaluation", "Run quizzes, coding drills, mock tests, and mistake tracking.", "TestingAgent", "BugDetectionSkill", 3.0),
                ("Final revision loop", "Compress notes, prioritize weak areas, and schedule exam-day review.", "MemoryAgent", "MemoryCompressionSkill", 2.0),
            ]
        else:
            phases = [
                ("Clarify objective", "Extract success criteria, constraints, risk level, and unknowns.", "PlanningAgent", "TaskPlanningSkill", 1.5),
                ("Create execution plan", "Break the goal into ordered tasks, dependencies, and milestones.", "PlanningAgent", "WorkflowOptimizerSkill", 2.0),
                ("Execute core work", "Perform the highest-value tasks using the relevant tools and skills.", "AutomationAgent", "BrowserAutomationSkill", 3.0),
                ("Validate output", "Check quality, accuracy, source coverage, and user intent match.", "QualityAgent", "CodeReviewSkill", 2.0),
                ("Learn and optimize", "Store lessons, update skills, compress memory, and recommend next steps.", "MemoryAgent", "MemoryCompressionSkill", 1.5),
            ]
        return [
            {
                "title": title,
                "description": description,
                "agent_type": agent_type,
                "skill_name": skill_name,
                "effort": effort,
                "confidence": 0.82,
            }
            for title, description, agent_type, skill_name, effort in phases
        ]

    def _upsert_task(
        self,
        goal_id: str,
        title: str,
        description: str,
        agent_type: str,
        skill_name: str,
        priority: float,
        estimated_effort: float,
        dependency_ids: list[str],
    ) -> dict[str, Any]:
        now = utc_now()
        fingerprint = stable_fingerprint(f"goal-task:{goal_id}:{title}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM goal_tasks WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode_task(existing)
            task_id = f"gtask_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO goal_tasks(
                    id, goal_id, parent_task_id, title, description, agent_type, skill_name,
                    priority, status, estimated_effort, deadline, dependency_ids, confidence,
                    fingerprint, created_at, updated_at
                )
                VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 'pending', ?, NULL, ?, 0.82, ?, ?, ?)
                """,
                (
                    task_id,
                    goal_id,
                    title,
                    description,
                    agent_type,
                    skill_name,
                    self._clamp(priority),
                    max(0.25, estimated_effort),
                    dumps([item for item in dependency_ids if item]),
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM goal_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._decode_task(row)

    def _upsert_milestone(self, goal_id: str, title: str, due_at: str | None, confidence: float) -> dict[str, Any]:
        now = utc_now()
        fingerprint = stable_fingerprint(f"goal-milestone:{goal_id}:{title}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM goal_milestones WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode_milestone(existing)
            milestone_id = f"gms_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO goal_milestones(id, goal_id, title, due_at, status, progress, confidence, fingerprint, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                """,
                (milestone_id, goal_id, title, due_at, self._clamp(confidence), fingerprint, now, now),
            )
            row = conn.execute("SELECT * FROM goal_milestones WHERE id = ?", (milestone_id,)).fetchone()
        return self._decode_milestone(row)

    def _record_event(self, goal_id: str, event_type: str, payload: dict[str, Any], confidence: float) -> None:
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                "INSERT INTO goal_events(goal_id, event_type, payload, confidence, created_at) VALUES (?, ?, ?, ?, ?)",
                (goal_id, event_type, dumps(payload), self._clamp(confidence), utc_now()),
            )

    def _path_exists(self, start_goal_id: str, target_goal_id: str, seen: set[str] | None = None) -> bool:
        seen = seen or set()
        if start_goal_id in seen:
            return False
        seen.add(start_goal_id)
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT depends_on_goal_id FROM goal_dependencies WHERE goal_id = ?",
                (start_goal_id,),
            ).fetchall()
        for row in rows:
            next_goal = row["depends_on_goal_id"]
            if next_goal == target_goal_id or self._path_exists(next_goal, target_goal_id, seen):
                return True
        return False

    def _require_goal(self, goal_id: str) -> dict[str, Any]:
        goal = self.get_goal(goal_id)
        if goal is None:
            raise ValueError(f"Unknown goal: {goal_id}")
        return goal

    def _decode_goal(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["milestones"] = loads(data.get("milestones"), [])
        data["execution_state"] = loads(data.get("execution_state"), {})
        return data

    def _decode_task(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["dependency_ids"] = loads(data.get("dependency_ids"), [])
        return data

    def _decode_milestone(self, row: Any) -> dict[str, Any]:
        return dict(row)

    def _decode_dependency(self, row: Any) -> dict[str, Any]:
        return dict(row)

    def _decode_event(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = loads(data.get("payload"), {})
        return data

    def _risk_score(self, title: str, context: str, deadline: str | None) -> float:
        text = f"{title} {context}".lower()
        score = 0.18
        if re.search(r"\b(payment|delete|password|submit|production|deploy|legal)\b", text):
            score += 0.35
        if re.search(r"\b(startup|business|deadline|exam|launch|client)\b", text):
            score += 0.2
        if deadline:
            score += 0.1
        return self._clamp(score)

    def _estimate_effort(self, title: str, context: str) -> float:
        text = f"{title} {context}".lower()
        base = 4.0
        if re.search(r"\b(startup|platform|production|complete|full|months)\b", text):
            base += 8.0
        if re.search(r"\b(app|backend|frontend|database|deploy|testing)\b", text):
            base += 6.0
        if re.search(r"\b(study|exam|notes|practice)\b", text):
            base += 3.0
        return round(base, 2)

    def _health(self, goal: dict[str, Any], progress: float, blocked_tasks: list[str]) -> str:
        if blocked_tasks:
            return "blocked"
        if float(goal.get("risk_score", 0)) >= 0.65 and progress < 50:
            return "at_risk"
        deadline = goal.get("deadline")
        if deadline:
            try:
                due = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                if due < datetime.now(timezone.utc) and progress < 100:
                    return "overdue"
            except ValueError:
                return "needs_review"
        return "healthy"

    def _distributed_due_date(self, deadline: str | None, index: int, total: int) -> str | None:
        if not deadline:
            return None
        try:
            due = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except ValueError:
            return None
        return due.isoformat() if index == total else None

    def _validate_deadline(self, deadline: str | None) -> None:
        if not deadline:
            return
        try:
            datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid goal deadline: {deadline}") from exc

    def _clean(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    def _merge_text(self, left: str, right: str) -> str:
        if not right or right.lower() in left.lower():
            return left
        return f"{left}\n{right}" if left else right

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _average(self, values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0
