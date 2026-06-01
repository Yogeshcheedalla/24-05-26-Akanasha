from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class UncertaintyCollaborationEngine:
    """Stops blind execution and asks the owner for help when confidence drops."""

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def evaluate(
        self,
        task: str,
        analysis: dict[str, Any],
        tool_plan: dict[str, Any],
        safety: dict[str, Any],
        predictions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        issues = self._issues(task, analysis, tool_plan, safety, predictions or {})
        if not issues:
            return {
                "status": "clear",
                "needs_user_input": False,
                "issues": [],
                "question": "",
                "confidence": round(1.0 - float(analysis.get("uncertainty_score", 0.35)) * 0.35, 3),
            }

        question = self._question(issues, task)
        confidence = round(max(0.18, 1.0 - (len(issues) * 0.12) - float(analysis.get("uncertainty_score", 0.5)) * 0.45), 3)
        now = utc_now()
        fingerprint = stable_fingerprint(f"{task}:{','.join(issue['type'] for issue in issues)}:{question}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM collaboration_questions WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing, deduplicated=True)
            question_id = f"collab_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO collaboration_questions(
                    id, task, trigger, issue_type, question, context,
                    confidence, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    task,
                    issues[0]["trigger"],
                    issues[0]["type"],
                    question,
                    dumps({"issues": issues, "analysis": analysis, "tool_plan": tool_plan, "safety": safety}),
                    confidence,
                    "awaiting_user",
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM collaboration_questions WHERE id = ?", (question_id,)).fetchone()
        return self._decode(row) if row else {"id": question_id, "needs_user_input": True, "question": question}

    def resolve(self, question_id: str, user_input: str) -> dict[str, Any]:
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM collaboration_questions WHERE id = ?", (question_id,)).fetchone()
            if not row:
                raise ValueError("Collaboration question not found")
            context = loads(row["context"], {})
            context["user_input"] = user_input
            conn.execute(
                """
                UPDATE collaboration_questions
                SET context = ?, status = 'resolved', updated_at = ?
                WHERE id = ?
                """,
                (dumps(context), now, question_id),
            )
            updated = conn.execute("SELECT * FROM collaboration_questions WHERE id = ?", (question_id,)).fetchone()
        return self._decode(updated) if updated else {"id": question_id, "status": "resolved"}

    def pending(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM collaboration_questions WHERE status = 'awaiting_user' ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _issues(
        self,
        task: str,
        analysis: dict[str, Any],
        tool_plan: dict[str, Any],
        safety: dict[str, Any],
        predictions: dict[str, Any],
    ) -> list[dict[str, str]]:
        lowered = task.lower()
        issues: list[dict[str, str]] = []
        if float(analysis.get("uncertainty_score", 0.0)) >= 0.68:
            issues.append({"type": "low_prediction_confidence", "trigger": "confidence_analysis"})
        if safety.get("requires_approval"):
            issues.append({"type": "approval_required", "trigger": "safety_system"})
        if tool_plan.get("blocked_tools"):
            issues.append({"type": "tool_permission_blocked", "trigger": "tool_layer"})
        if re.search(r"\b(any|something|whatever|best|good|cheap|nearby|later|soon)\b", lowered):
            issues.append({"type": "missing_specific_information", "trigger": "requirement_extraction"})
        if re.search(r"\b(two|multiple|conflicting|different|not matching|wrong)\b", lowered):
            issues.append({"type": "conflicting_information", "trigger": "result_validation"})
        if re.search(r"\b(login|sign in|authentication|auth|expired)\b", lowered):
            issues.append({"type": "authentication_issue", "trigger": "service_access"})
        if re.search(r"\b(failed|error|crash|stuck|blocked|dead end|not working)\b", lowered):
            issues.append({"type": "execution_blocker", "trigger": "failure_monitor"})
        if predictions.get("confidence") and float(predictions.get("confidence", 0.0)) < 0.55:
            issues.append({"type": "low_prediction_confidence", "trigger": "predictive_assistant"})
        return self._dedupe(issues)

    def _question(self, issues: list[dict[str, str]], task: str) -> str:
        issue_type = issues[0]["type"]
        if issue_type == "approval_required":
            return "This action needs your approval before I continue. Should I proceed with the verified plan?"
        if issue_type == "tool_permission_blocked":
            return "A required tool needs permission before execution. Do you want me to continue with the approved tools only, or approve the blocked tool?"
        if issue_type == "missing_specific_information":
            return "I need one more detail to avoid guessing. Which option or constraint should I prioritize?"
        if issue_type == "conflicting_information":
            return "I found conflicting information. Which source or result should I trust first?"
        if issue_type == "authentication_issue":
            return "Authentication looks required or expired. Please sign in or confirm which account I should use."
        if issue_type == "execution_blocker":
            return "This workflow hit a blocker. Should I retry, switch tools, or wait for your instruction?"
        return "My confidence is low here. Can you confirm the missing detail before I continue?"

    def _dedupe(self, issues: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[tuple[str, str]] = set()
        result: list[dict[str, str]] = []
        for issue in issues:
            key = (issue["type"], issue["trigger"])
            if key not in seen:
                result.append(issue)
                seen.add(key)
        return result

    def _decode(self, row: Any, deduplicated: bool = False) -> dict[str, Any]:
        data = dict(row)
        data["context"] = loads(data.get("context"), {})
        data["issues"] = data["context"].get("issues", [])
        data["needs_user_input"] = data.get("status") == "awaiting_user"
        data["deduplicated"] = deduplicated
        return data
