from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from ..database.store import CognitiveStore, dumps, loads, stable_fingerprint, utc_now


SUPPORTED_TOOL_KINDS = {"mcp", "api", "browser", "desktop", "database", "plugin"}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str
    capabilities: list[str]
    requires_approval: bool = False
    risk_level: str = "low"
    enabled: bool = True


class UniversalToolLayer:
    """Governed registry for every action surface Akansha can use.

    The layer plans tool usage and approval boundaries. It does not execute
    browser, desktop, database, or plugin actions directly.
    """

    def __init__(self, store: CognitiveStore) -> None:
        self.store = store

    def ensure_defaults(self) -> list[dict[str, Any]]:
        defaults = [
            ToolSpec("MCP Connector", "mcp", ["context_fetch", "structured_tool_call"], False, "low"),
            ToolSpec("Web/API Gateway", "api", ["live_data", "citations", "validation"], False, "medium"),
            ToolSpec("Browser Automation", "browser", ["open_url", "click", "scroll", "extract"], True, "high"),
            ToolSpec("Desktop Automation", "desktop", ["app_control", "window_control", "notifications"], True, "critical"),
            ToolSpec("Hermes Database", "database", ["memory_read", "skill_read", "audit_write"], False, "medium"),
            ToolSpec("Plugin Runtime", "plugin", ["documents", "spreadsheets", "presentations"], False, "medium"),
            ToolSpec("Shopping Services Gateway", "api", ["commerce_search", "product_compare", "price_history", "review_analysis"], False, "medium"),
            ToolSpec("Booking Services Gateway", "api", ["booking_search", "availability_recheck", "schedule_validation"], False, "medium"),
            ToolSpec("Calendar and Email Connector", "plugin", ["calendar_check", "email_summary", "follow_up"], True, "high"),
            ToolSpec("Payment Guard", "api", ["payment_precheck", "fraud_detection", "approval_gate"], True, "critical"),
            ToolSpec("Maps and Local Services", "api", ["maps", "distance_estimate", "restaurant_lookup"], False, "medium"),
            ToolSpec("Education Builder", "plugin", ["notes", "quiz", "flashcards", "study_plan", "formula_sheet"], False, "medium"),
            ToolSpec("Data Processing Runtime", "plugin", ["data_analysis", "tables", "charts", "csv", "xlsx"], False, "medium"),
            ToolSpec("Multimodal Analyzer", "plugin", ["multimodal_context", "image_analysis", "video_summary", "audio_transcription"], False, "medium"),
            ToolSpec("API Workflow Gateway", "api", ["api_gateway", "webhook", "endpoint_validation", "integration"], True, "high"),
        ]
        return [self.register_tool(spec) for spec in defaults]

    def register_tool(self, spec: ToolSpec) -> dict[str, Any]:
        if spec.kind not in SUPPORTED_TOOL_KINDS:
            raise ValueError(f"Unsupported tool kind: {spec.kind}")
        if not spec.name.strip():
            raise ValueError("Tool name cannot be empty")
        fingerprint = stable_fingerprint(f"{spec.kind}:{spec.name}")
        now = utc_now()
        with self.store.connect(self.store.files.agents) as conn:
            existing = conn.execute("SELECT * FROM tool_registry WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE tool_registry
                    SET capabilities = ?, requires_approval = ?, risk_level = ?, enabled = ?, updated_at = ?
                    WHERE fingerprint = ?
                    """,
                    (
                        dumps(spec.capabilities),
                        int(spec.requires_approval),
                        spec.risk_level,
                        int(spec.enabled),
                        now,
                        fingerprint,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO tool_registry(
                        id, name, kind, capabilities, requires_approval,
                        risk_level, enabled, fingerprint, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"tool_{uuid4().hex}",
                        spec.name,
                        spec.kind,
                        dumps(spec.capabilities),
                        int(spec.requires_approval),
                        spec.risk_level,
                        int(spec.enabled),
                        fingerprint,
                        now,
                        now,
                    ),
                )
        return self.get_by_fingerprint(fingerprint) or asdict(spec)

    def list_tools(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM tool_registry"
        params: tuple[Any, ...] = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY kind, name"
        with self.store.connect(self.store.files.agents) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._decode(row) for row in rows]

    def plan_for_task(self, task: str, required_tools: list[str], approved: bool = False) -> dict[str, Any]:
        self.ensure_defaults()
        tools = self.list_tools(enabled_only=True)
        selected: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        required = set(required_tools)
        for tool in tools:
            if not self._matches(tool, required, task):
                continue
            entry = {
                "tool_id": tool["id"],
                "name": tool["name"],
                "kind": tool["kind"],
                "risk_level": tool["risk_level"],
                "capabilities": tool["capabilities"],
            }
            if tool["requires_approval"] and not approved:
                blocked.append({**entry, "reason": "approval_required"})
            else:
                selected.append(entry)
        return {
            "selected_tools": selected,
            "blocked_tools": blocked,
            "approval_required": bool(blocked),
            "execution_policy": "plan_only_governed_action_layer",
        }

    def get_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        with self.store.connect(self.store.files.agents) as conn:
            row = conn.execute("SELECT * FROM tool_registry WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return self._decode(row) if row else None

    def _matches(self, tool: dict[str, Any], required_tools: set[str], task: str) -> bool:
        lowered = task.lower()
        capabilities = set(tool["capabilities"])
        if "web_search" in required_tools and tool["kind"] == "api":
            return True
        if "browser_automation" in required_tools and tool["kind"] == "browser":
            return True
        if "desktop_control" in required_tools and tool["kind"] == "desktop":
            return True
        if "artifact_generation" in required_tools and (tool["kind"] == "plugin" or "documents" in capabilities):
            return True
        if {"repo_read", "tests"} & required_tools and tool["kind"] in {"database", "plugin"}:
            return True
        if "memory_recall" in required_tools and tool["kind"] == "database":
            return True
        if "data_analysis" in required_tools and "data_analysis" in capabilities:
            return True
        if "multimodal_context" in required_tools and "multimodal_context" in capabilities:
            return True
        if "api_gateway" in required_tools and "api_gateway" in capabilities:
            return True
        if {"commerce_search", "verification_recheck", "booking_search", "calendar_check", "life_automation", "concierge", "approval_gate"} & required_tools:
            if "commerce_search" in required_tools and "commerce_search" in capabilities:
                return True
            if "booking_search" in required_tools and "booking_search" in capabilities:
                return True
            if "verification_recheck" in required_tools and {"validation", "availability_recheck", "fraud_detection"} & capabilities:
                return True
            if "calendar_check" in required_tools and "calendar_check" in capabilities:
                return True
            if "life_automation" in required_tools and {"notifications", "email_summary", "calendar_check"} & capabilities:
                return True
            if "concierge" in required_tools and {"maps", "calendar_check", "restaurant_lookup"} & capabilities:
                return True
            if "approval_gate" in required_tools and "approval_gate" in capabilities:
                return True
        return tool["kind"] in lowered

    def _decode(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["capabilities"] = loads(data.get("capabilities"), [])
        data["requires_approval"] = bool(data.get("requires_approval"))
        data["enabled"] = bool(data.get("enabled"))
        return data
