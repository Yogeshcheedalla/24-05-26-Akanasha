from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


class UniversalAutomationLayer:
    """Plans browser, desktop, API, document, file, email, and calendar actions."""

    ACTION_CAPABILITIES = {
        "browser": ["open_url", "click", "scroll", "extract", "form_fill"],
        "desktop": ["app_control", "window_control", "notifications", "media_control"],
        "documents": ["pdf", "docx", "pptx", "xlsx", "csv", "json", "zip"],
        "files": ["create", "read", "organize", "export", "verify"],
        "communication": ["email_summary", "follow_up", "draft_message"],
        "calendar": ["availability_check", "reminder", "schedule_event"],
        "api": ["live_data", "webhook", "database_update", "service_call"],
        "data_processing": ["table", "chart", "analysis", "cleaning"],
        "research": ["source_search", "citation", "cross_check"],
        "development": ["repo_read", "patch", "test", "build"],
    }

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def plan(
        self,
        task: str,
        analysis: dict[str, Any],
        tool_plan: dict[str, Any],
        approved: bool,
    ) -> dict[str, Any]:
        surfaces = self._surfaces(analysis)
        action_plan = self._action_plan(surfaces, analysis, tool_plan, approved)
        confidence = round(max(0.3, 0.9 - float(analysis.get("uncertainty_score", 0.4)) * 0.35), 3)
        status = "approval_required" if action_plan["approval_required"] and not approved else "ready"
        now = utc_now()
        fingerprint = stable_fingerprint(f"{task}:{','.join(surfaces)}:{status}")
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM automation_plans WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                return self._decode(existing, deduplicated=True)
            plan_id = f"auto_{uuid4().hex}"
            conn.execute(
                """
                INSERT INTO automation_plans(
                    id, task, surfaces, action_plan, required_permissions,
                    approval_state, confidence, status, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    task,
                    dumps(surfaces),
                    dumps(action_plan),
                    dumps(action_plan["required_permissions"]),
                    "approved" if approved else "plan_only",
                    confidence,
                    status,
                    fingerprint,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM automation_plans WHERE id = ?", (plan_id,)).fetchone()
        return self._decode(row) if row else {"id": plan_id, "status": status}

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM automation_plans ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _surfaces(self, analysis: dict[str, Any]) -> list[str]:
        tools = set(analysis.get("tools", []))
        intent = analysis.get("intent")
        surfaces: list[str] = []
        if "browser_automation" in tools:
            surfaces.append("browser")
        if "desktop_control" in tools:
            surfaces.append("desktop")
        if "artifact_generation" in tools or intent == "artifact_generation":
            surfaces.extend(["documents", "files"])
        if "calendar_check" in tools or intent in {"booking", "life_automation", "concierge"}:
            surfaces.append("calendar")
        if "web_search" in tools or intent == "live_research":
            surfaces.extend(["api", "research"])
        if intent == "coding":
            surfaces.append("development")
        if intent in {"commerce", "booking", "concierge"}:
            surfaces.append("api")
        if intent == "life_automation":
            surfaces.extend(["communication", "desktop"])
        if not surfaces:
            surfaces.append("api")
        return list(dict.fromkeys(surfaces))

    def _action_plan(
        self,
        surfaces: list[str],
        analysis: dict[str, Any],
        tool_plan: dict[str, Any],
        approved: bool,
    ) -> dict[str, Any]:
        steps = []
        permissions = []
        for surface in surfaces:
            capabilities = self.ACTION_CAPABILITIES.get(surface, [])
            steps.append({"surface": surface, "capabilities": capabilities, "mode": "governed_plan"})
            if surface in {"browser", "desktop", "calendar", "communication"}:
                permissions.append(f"{surface}_permission")
        approval_required = bool(tool_plan.get("blocked_tools")) or analysis.get("risk_level") in {"high", "critical"}
        return {
            "steps": steps,
            "required_permissions": list(dict.fromkeys(permissions)),
            "blocked_tools": tool_plan.get("blocked_tools", []),
            "approval_required": approval_required and not approved,
            "rate_limit": {"max_actions_per_minute": 20, "sensitive_actions_per_minute": 2},
            "rollback": "restore_previous_state_or_keep_plan_only_audit",
            "verification_loop": ["precheck", "execute_allowed_step", "verify_result", "record_learning"],
        }

    def _decode(self, row: Any, deduplicated: bool = False) -> dict[str, Any]:
        data = dict(row)
        data["surfaces"] = loads(data.get("surfaces"), [])
        data["action_plan"] = loads(data.get("action_plan"), {})
        data["required_permissions"] = loads(data.get("required_permissions"), [])
        data["deduplicated"] = deduplicated
        return data
