from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, utc_now
from ..safety.validator import SafetyValidator
from ..tools.universal_tool_layer import UniversalToolLayer
from .common import clamp


class MultiServiceExecutionBus:
    """Governed router for real-world services without bypassing approval gates."""

    SERVICE_MAP = {
        "commerce": ["shopping_services", "browser", "payments", "email"],
        "booking": ["calendar", "maps", "booking_services", "payments", "email"],
        "life_automation": ["calendar", "notifications", "email", "tasks"],
        "concierge": ["maps", "calendar", "browser", "email", "documents"],
        "verification": ["browser", "api", "database"],
    }

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.tools = UniversalToolLayer(store)
        self.safety = SafetyValidator()

    def plan(self, request_type: str, payload: dict[str, Any], approved: bool = False) -> dict[str, Any]:
        event_id = f"bus_{uuid4().hex}"
        services = self._services(request_type, payload)
        required_tools = self._required_tools(services)
        tool_plan = self.tools.plan_for_task(
            f"{request_type} {' '.join(services)}",
            required_tools,
            approved=approved,
        )
        risk_level = "critical" if "payments" in services else "high" if {"browser", "desktop"} & set(services) else "medium"
        safety = self.safety.validate_learning_action(
            {
                "type": request_type,
                "tools": required_tools,
                "risk_level": risk_level,
                "loop_key": f"execution_bus:{request_type}",
                "approved": approved,
            }
        )
        auth_requirements = self._auth_requirements(services)
        execution_steps = self._execution_steps(services, approved)
        result = {
            "id": event_id,
            "request_type": request_type,
            "service_plan": {"services": services, "tool_plan": tool_plan},
            "auth_requirements": auth_requirements,
            "execution_steps": execution_steps,
            "monitoring": {
                "audit_log": True,
                "rollback_strategy": "cancel_or_revert_reversible_steps_when_supported",
                "rate_limit_policy": "bounded_by_service_and_user_approval",
            },
            "approval_state": "approved" if approved and safety["allowed"] else "requires_owner_approval",
            "result": {
                "executed": False,
                "reason": "planning_bus_only_until_service_auth_and_owner_approval",
                "safety": safety,
            },
            "confidence": self._confidence(tool_plan, safety, auth_requirements),
            "created_at": utc_now(),
        }
        self._store(result)
        return result

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(
                "SELECT * FROM execution_bus_events ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _services(self, request_type: str, payload: dict[str, Any]) -> list[str]:
        base = list(self.SERVICE_MAP.get(request_type, ["api", "database"]))
        if payload.get("needs_desktop"):
            base.append("desktop")
        if payload.get("needs_documents"):
            base.append("documents")
        return list(dict.fromkeys(base))

    def _required_tools(self, services: list[str]) -> list[str]:
        tools: list[str] = []
        if any(service in services for service in ["shopping_services", "booking_services", "api"]):
            tools.append("web_search")
        if "browser" in services:
            tools.append("browser_automation")
        if "desktop" in services:
            tools.append("desktop_control")
        if "documents" in services:
            tools.append("artifact_generation")
        if "database" in services:
            tools.append("memory_read")
        return sorted(set(tools))

    def _auth_requirements(self, services: list[str]) -> list[dict[str, Any]]:
        sensitive = {"payments", "email", "calendar", "booking_services", "shopping_services"}
        return [
            {
                "service": service,
                "requires_user_connection": service in sensitive,
                "scope_policy": "least_privilege",
                "approval_required": service in sensitive,
            }
            for service in services
        ]

    def _execution_steps(self, services: list[str], approved: bool) -> list[dict[str, Any]]:
        steps = [{"step": "select_services", "services": services}]
        steps.append({"step": "authenticate_required_services", "status": "ready" if approved else "waiting_for_owner"})
        steps.append({"step": "execute_reversible_reads", "status": "allowed"})
        steps.append({"step": "verify_before_irreversible_action", "status": "mandatory"})
        steps.append({"step": "execute_irreversible_action", "status": "blocked_until_explicit_approval"})
        steps.append({"step": "monitor_and_record_learning", "status": "planned"})
        return steps

    def _confidence(self, tool_plan: dict[str, Any], safety: dict[str, Any], auth: list[dict[str, Any]]) -> float:
        auth_penalty = min(0.18, sum(1 for item in auth if item["requires_user_connection"]) * 0.03)
        approval_penalty = 0.12 if tool_plan.get("approval_required") else 0.0
        safety_bonus = 0.12 if safety.get("allowed") else 0.0
        return round(clamp(0.68 + safety_bonus - auth_penalty - approval_penalty), 3)

    def _store(self, result: dict[str, Any]) -> None:
        with self.store.connect(self.store.files.agents) as conn:
            conn.execute(
                """
                INSERT INTO execution_bus_events(
                    id, request_type, service_plan, auth_requirements,
                    execution_steps, monitoring, approval_state, result,
                    confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["id"],
                    result["request_type"],
                    dumps(result["service_plan"]),
                    dumps(result["auth_requirements"]),
                    dumps(result["execution_steps"]),
                    dumps(result["monitoring"]),
                    result["approval_state"],
                    dumps(result["result"]),
                    result["confidence"],
                    result["created_at"],
                ),
            )

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("service_plan", "auth_requirements", "execution_steps", "monitoring", "result"):
            data[key] = loads(data.get(key), [] if key in {"auth_requirements", "execution_steps"} else {})
        return data
