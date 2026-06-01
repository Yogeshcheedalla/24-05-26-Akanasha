from __future__ import annotations

import re
from typing import Any

from .task_decomposer import TaskDecomposer


class InputUnderstandingEngine:
    def __init__(self) -> None:
        self.decomposer = TaskDecomposer()

    def understand(self, text: str) -> dict[str, Any]:
        lowered = text.lower()
        steps = self.decomposer.decompose(text)
        required_tools = self._tools(lowered)
        risk_level = (
            "critical"
            if re.search(r"\b(delete|payment|pay|purchase|buy|book|confirm|submit|send email|password)\b", lowered)
            else "high"
            if "desktop" in lowered
            else "low"
        )
        emotion = "stressed" if re.search(r"\b(urgent|angry|frustrated|wrong|failed|not working)\b", lowered) else "neutral"
        intent = self._intent(lowered)
        return {
            "intent": intent,
            "priority": "high" if risk_level in {"high", "critical"} or "urgent" in lowered else "normal",
            "emotion": emotion,
            "required_tools": required_tools,
            "task_complexity": min(100, len(steps) * max(1, len(required_tools)) * 10),
            "memory_relevance": 0.8 if re.search(r"\b(remember|again|previous|last time)\b", lowered) else 0.4,
            "risk_level": risk_level,
            "steps": steps,
        }

    def _intent(self, lowered: str) -> str:
        if re.search(r"\b(book|booking|reserve|reservation|flight|hotel|restaurant|appointment|tickets?|transport|cab|taxi)\b", lowered):
            return "booking"
        if re.search(r"\b(buy|purchase|shopping|compare products?|best .* under|price compare|delivery time|reviews?)\b", lowered):
            return "commerce"
        if re.search(r"\b(remind|reminder|alert|alarm|subscription|bill|deadline|follow up|follow-up|schedule task)\b", lowered):
            return "life_automation"
        if re.search(r"\b(concierge|trip plan|travel plan|gift recommendation|event planning|daily schedule|meeting coordination)\b", lowered):
            return "concierge"
        if re.search(r"\b(goal|milestone|roadmap|chief of staff|startup|long[- ]term|project plan)\b", lowered) or re.search(
            r"\bin \d+\s*(day|week|month|year)s?\b", lowered
        ):
            return "goal_management"
        if re.search(r"\b(teach|explain|quiz|flashcards?|notes?|study plan|solve math|formula|education)\b", lowered):
            return "education"
        if re.search(r"\b(email|message|communicate|draft|follow up|follow-up|send reply|reply to)\b", lowered):
            return "communication"
        if re.search(r"\b(clean data|analyze data|table|chart|csv|spreadsheet|dataset)\b", lowered):
            return "data_processing"
        if re.search(r"\b(video|audio|image|media|youtube|transcribe|summarize video)\b", lowered):
            return "media"
        if re.search(r"\b(files?|folder|organize|rename|move|zip|extract)\b", lowered):
            return "file_management"
        if re.search(r"\b(api|webhook|database|endpoint|integration)\b", lowered):
            return "api_workflow"
        if re.search(r"\b(system|settings|install|startup|service|process|health check)\b", lowered):
            return "system_management"
        if re.search(r"\b(search|latest|news|score|price|weather)\b", lowered):
            return "live_research"
        if re.search(r"\b(debug|fix|patch|bug|issue|code|test|tests|build|deploy)\b", lowered):
            return "coding"
        if re.search(r"\b(pdf|excel|ppt|docx|csv|json|file|report)\b", lowered):
            return "artifact_generation"
        if re.search(r"\b(open|click|scroll|desktop|browser|submit)\b", lowered):
            return "automation"
        return "conversation"

    def _tools(self, lowered: str) -> list[str]:
        tools: list[str] = []
        if re.search(r"\b(buy|purchase|shopping|compare products?|price compare|delivery time|reviews?)\b", lowered):
            tools.extend(["commerce_search", "verification_recheck", "approval_gate"])
        if re.search(r"\b(book|booking|reserve|reservation|flight|hotel|restaurant|appointment|tickets?|transport|cab|taxi)\b", lowered):
            tools.extend(["booking_search", "calendar_check", "verification_recheck", "approval_gate"])
        if re.search(r"\b(remind|reminder|alert|alarm|subscription|bill|deadline|follow up|follow-up|schedule task)\b", lowered):
            tools.extend(["life_automation", "calendar_check", "approval_gate"])
        if re.search(r"\b(concierge|trip plan|travel plan|gift recommendation|event planning|daily schedule|meeting coordination)\b", lowered):
            tools.extend(["concierge", "calendar_check", "verification_recheck"])
        if re.search(r"\b(goal|milestone|roadmap|chief of staff|startup|long[- ]term|project plan)\b", lowered) or re.search(
            r"\bin \d+\s*(day|week|month|year)s?\b", lowered
        ):
            tools.extend(["goal_graph", "project_manager"])
        if re.search(r"\b(teach|explain|quiz|flashcards?|notes?|study plan|solve math|formula|education)\b", lowered):
            tools.extend(["artifact_generation", "memory_recall"])
        if re.search(r"\b(email|message|communicate|draft|follow up|follow-up|send reply|reply to)\b", lowered):
            tools.extend(["calendar_check", "approval_gate"])
        if re.search(r"\b(clean data|analyze data|table|chart|csv|spreadsheet|dataset)\b", lowered):
            tools.extend(["artifact_generation", "data_analysis"])
        if re.search(r"\b(video|audio|image|media|youtube|transcribe|summarize video)\b", lowered):
            tools.extend(["multimodal_context", "artifact_generation"])
        if re.search(r"\b(files?|folder|organize|rename|move|zip|extract)\b", lowered):
            tools.extend(["artifact_generation", "desktop_control"])
        if re.search(r"\b(api|webhook|database|endpoint|integration)\b", lowered):
            tools.extend(["api_gateway", "tests"])
        if re.search(r"\b(system|settings|install|startup|service|process|health check)\b", lowered):
            tools.extend(["desktop_control", "tests"])
        if re.search(r"\b(search|latest|news|score|price|weather)\b", lowered):
            tools.append("web_search")
        if re.search(r"\b(pdf|excel|ppt|docx|csv|json|file|report)\b", lowered):
            tools.append("artifact_generation")
        if re.search(r"\b(open|click|scroll|desktop|browser|submit)\b", lowered):
            tools.extend(["browser_automation", "desktop_control"])
        if re.search(r"\b(debug|fix|patch|bug|issue|code|test|tests|build|deploy)\b", lowered):
            tools.extend(["repo_read", "tests"])
        return sorted(set(tools))
