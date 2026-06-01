from __future__ import annotations

from typing import Any

from ..database.store import CognitiveStore
from .agent_factory import AgentFactory


DEFAULT_AGENT_TOOLS = {
    "ResearchAgent": ["web_search", "citation_check"],
    "CodingAgent": ["repo_read", "tests", "patch"],
    "MemoryAgent": ["memory_recall", "memory_compression"],
    "BrowserAgent": ["browser_automation"],
    "VoiceAgent": ["asr", "tts", "vad"],
    "TestingAgent": ["unit_tests", "type_check"],
    "SecurityAgent": ["permissions", "risk_validation"],
    "QualityAgent": ["review", "validation"],
    "PlanningAgent": ["task_decomposition"],
    "AnalysisAgent": ["data_analysis"],
    "CreativeAgent": ["content_generation"],
    "DeploymentAgent": ["build", "release"],
    "AutomationAgent": ["desktop_control"],
    "DataAgent": ["tables", "files"],
    "FileAgent": ["filesystem", "artifact_generation"],
    "ShoppingAgent": ["commerce_search", "product_compare", "price_history", "approval_gate"],
    "BookingAgent": ["booking_search", "calendar_check", "availability_recheck", "approval_gate"],
    "ConciergeAgent": ["travel_planning", "meeting_coordination", "gift_recommendations", "schedule_optimization"],
}

WORKER_SPECIALIZATION_BY_AGENT = {
    "ResearchAgent": "ResearchWorker",
    "CodingAgent": "DebugWorker",
    "AnalysisAgent": "AnalysisWorker",
    "AutomationAgent": "AutomationWorker",
    "BrowserAgent": "AutomationWorker",
    "DataAgent": "AnalysisWorker",
    "TestingAgent": "DebugWorker",
    "ShoppingAgent": "ResearchWorker",
    "BookingAgent": "AutomationWorker",
    "ConciergeAgent": "PlanningWorker",
}


class Coordinator:
    def __init__(self, store: CognitiveStore) -> None:
        self.store = store
        self.factory = AgentFactory(store)

    def complexity_score(
        self,
        task_steps: int,
        required_tools: int,
        estimated_runtime: float,
        uncertainty_score: float,
        dependencies: int = 1,
    ) -> float:
        return round(
            (task_steps * 5)
            + (max(1, required_tools) * 5)
            + (max(1, dependencies) * 3)
            + (max(0.1, uncertainty_score) * 20)
            + min(20.0, estimated_runtime),
            3,
        )

    def recommended_worker_count(self, complexity: float) -> int:
        if complexity < 30:
            return 0
        if complexity < 60:
            return 2
        if complexity < 90:
            return 4
        return 6

    def ensure_core_agents(self) -> list[dict[str, Any]]:
        return self.factory.ensure_persistent_core()

    def assign_temporary_workers(self, task: str, required_types: list[str], complexity: float) -> list[dict[str, Any]]:
        count = min(self.recommended_worker_count(complexity), 6)
        workers: list[dict[str, Any]] = []
        worker_seed = [agent_type for agent_type in required_types if agent_type in WORKER_SPECIALIZATION_BY_AGENT]
        if not worker_seed:
            worker_seed = ["PlanningAgent"]
        for index in range(count):
            agent_type = worker_seed[index % len(worker_seed)]
            worker_kind = WORKER_SPECIALIZATION_BY_AGENT.get(agent_type, "AnalysisWorker")
            workers.append(
                self.factory.create_temporary_worker(
                    worker_name=f"{worker_kind}_{index + 1}",
                    specialization=agent_type,
                    task=f"Temporary isolated work on: {task}",
                    tools=DEFAULT_AGENT_TOOLS.get(agent_type, []),
                )
            )
        return workers

    def route_skills(self, task: str, intent: str) -> list[str]:
        lowered = task.lower()
        mapping = {
            "artifact_generation": ["PDFGenerationSkill", "SpreadsheetAnalysisSkill", "PresentationBuilderSkill"],
            "live_research": ["DeepResearchSkill", "NewsIntelligenceSkill"],
            "automation": ["BrowserAutomationSkill", "VoiceCommandSkill"],
            "coding": ["AutonomousDebugSkill", "CodeReviewSkill", "GitDeploySkill"],
            "goal_management": ["TaskPlanningSkill", "WorkflowOptimizerSkill", "MemoryCompressionSkill", "DeepResearchSkill"],
            "commerce": ["ShoppingSkill", "ProductComparisonSkill", "VerificationSkill", "WorkflowOptimizerSkill"],
            "booking": ["BookingSkill", "ScheduleValidationSkill", "VerificationSkill", "WorkflowOptimizerSkill"],
            "life_automation": ["ReminderSkill", "LifeAutomationSkill", "WorkflowOptimizerSkill"],
            "concierge": ["ConciergeSkill", "TaskPlanningSkill", "VerificationSkill", "WorkflowOptimizerSkill"],
            "education": ["StudyPlanSkill", "QuizGenerationSkill", "PDFGenerationSkill", "WorkflowOptimizerSkill"],
            "communication": ["EmailSkill", "FollowUpSkill", "VerificationSkill", "WorkflowOptimizerSkill"],
            "data_processing": ["SpreadsheetAnalysisSkill", "DataCleaningSkill", "WorkflowOptimizerSkill"],
            "media": ["VideoSummarySkill", "ImageAnalysisSkill", "PresentationBuilderSkill", "WorkflowOptimizerSkill"],
            "file_management": ["FileOrganizationSkill", "VerificationSkill", "WorkflowOptimizerSkill"],
            "api_workflow": ["APIWorkflowSkill", "AutonomousDebugSkill", "TestingSkill", "WorkflowOptimizerSkill"],
            "system_management": ["SystemHealthSkill", "AutomationSkill", "VerificationSkill", "WorkflowOptimizerSkill"],
            "conversation": ["MemoryCompressionSkill", "WorkflowOptimizerSkill"],
        }
        routed = list(mapping.get(intent, ["WorkflowOptimizerSkill"]))
        if any(word in lowered for word in ["research", "latest", "news", "sources", "citations"]):
            routed.extend(["DeepResearchSkill", "NewsIntelligenceSkill"])
        if any(word in lowered for word in ["pdf", "excel", "ppt", "presentation", "report", "csv", "json"]):
            routed.extend(["PDFGenerationSkill", "SpreadsheetAnalysisSkill", "PresentationBuilderSkill"])
        deduped: list[str] = []
        for skill in routed:
            if skill not in deduped:
                deduped.append(skill)
        return deduped

    def resource_allocation(self, complexity: float, worker_count: int) -> dict[str, Any]:
        return {
            "mode": "persistent_core_only" if worker_count == 0 else "core_plus_temporary_workers",
            "temporary_worker_count": worker_count,
            "token_budget_hint": "low" if complexity < 30 else "medium" if complexity < 90 else "high",
            "latency_strategy": "single-pass" if worker_count == 0 else "parallel-worker-merge",
        }

    def merge_results(self, worker_results: list[dict[str, Any]]) -> dict[str, Any]:
        if not worker_results:
            return {"status": "core_agents_only", "confidence": 0.72, "merged_findings": []}
        confidence = sum(float(result.get("confidence", 0.5)) for result in worker_results) / len(worker_results)
        return {
            "status": "merged",
            "confidence": round(confidence, 4),
            "merged_findings": [result.get("result", "") for result in worker_results if result.get("result")],
        }
