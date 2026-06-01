from __future__ import annotations

import re
from typing import Any


class AdaptiveUIEngine:
    """Selects the user-facing mode without mutating frontend layout."""

    MODES = {"coding", "research", "startup", "creative", "learning", "voice", "business", "planning"}

    def mode_for_task(self, task: str, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
        lowered = task.lower()
        intent = (analysis or {}).get("intent", "")
        if "voice" in lowered or "speech" in lowered or "avatar" in lowered:
            mode = "voice"
        elif intent == "goal_management" or re.search(r"\b(startup|mvp|milestone|goal|roadmap|chief of staff)\b", lowered):
            mode = "startup"
        elif intent == "coding" or re.search(r"\b(code|debug|test|repo|deploy)\b", lowered):
            mode = "coding"
        elif intent == "live_research" or re.search(r"\b(research|latest|news|source|citation)\b", lowered):
            mode = "research"
        elif intent in {"commerce", "booking", "concierge"} or re.search(r"\b(buy|shopping|book|booking|hotel|flight|restaurant|concierge)\b", lowered):
            mode = "business"
        elif intent == "education" or re.search(r"\b(learn|study|quiz|flashcard|notes|exam|education)\b", lowered):
            mode = "learning"
        elif intent in {"life_automation", "file_management"} or re.search(r"\b(plan|todo|schedule|deadline|workflow)\b", lowered):
            mode = "planning"
        elif intent in {"communication", "data_processing"} or re.search(r"\b(business|invoice|market|analytics|report)\b", lowered):
            mode = "business"
        elif intent == "media" or re.search(r"\b(image|creative|design|story|presentation)\b", lowered):
            mode = "creative"
        elif intent in {"api_workflow", "system_management"}:
            mode = "coding"
        else:
            mode = "planning" if len(task) > 160 else "research"
        return self._config(mode)

    def _config(self, mode: str) -> dict[str, Any]:
        base = {
            "mode": mode,
            "density": "balanced",
            "primary_panels": ["conversation", "sources", "actions"],
            "response_style": "concise_with_audit",
        }
        configs = {
            "coding": {
                "primary_panels": ["diff", "tests", "terminal", "conversation"],
                "accent": "code_quality",
                "default_artifacts": ["patch", "test_report"],
            },
            "research": {
                "primary_panels": ["answer", "source_table", "confidence", "timeline"],
                "accent": "citations",
                "default_artifacts": ["table", "summary"],
            },
            "startup": {
                "primary_panels": ["goals", "milestones", "risks", "opportunities", "agents"],
                "accent": "executive_brain",
                "default_artifacts": ["roadmap", "decision_report"],
            },
            "learning": {
                "primary_panels": ["concepts", "examples", "quiz", "study_plan"],
                "accent": "education",
                "default_artifacts": ["notes", "flashcards", "pdf"],
            },
            "voice": {
                "primary_panels": ["avatar", "live_transcript", "interruptions", "language_state"],
                "accent": "low_latency",
                "default_artifacts": ["transcript"],
            },
            "planning": {
                "primary_panels": ["workflow", "todo", "calendar", "risks"],
                "accent": "execution",
                "default_artifacts": ["checklist"],
            },
            "business": {
                "primary_panels": ["metrics", "tables", "charts", "exports"],
                "accent": "decision_support",
                "default_artifacts": ["xlsx", "pdf"],
            },
            "creative": {
                "primary_panels": ["canvas", "variants", "assets", "exports"],
                "accent": "visual_output",
                "default_artifacts": ["png", "pptx"],
            },
        }
        base.update(configs.get(mode, {}))
        return base
