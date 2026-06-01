from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..learning.continuous_loop import ContinuousLearningLoop
from ..orchestrator import HermesCognitiveOS
from ..simulator import DEFAULT_SIMULATION_TASKS, HermesSimulator
from ..tools.universal_tool_layer import ToolSpec


router = APIRouter(prefix="/api/cognitive", tags=["Akansha Hermes Cognitive OS"])
_os = HermesCognitiveOS()


class MemoryCreateRequest(BaseModel):
    category: str
    content: str
    importance_score: float = Field(ge=0, le=1)
    source: str = "user"
    confidence: float = Field(default=0.75, ge=0, le=1)


class ShortTermRequest(BaseModel):
    session_id: str = "default"
    conversation: str
    tool_usage: list[str] = []
    context_score: float = Field(default=0.5, ge=0, le=1)


class RecallRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=10)


class ExperienceRequest(BaseModel):
    task: str
    goal: str
    actions_taken: list[str]
    tools_used: list[str]
    agents_used: list[str] = []
    errors: list[str] = []
    successful_steps: list[str]
    time_taken: float = 0.0
    feedback: str = ""
    score: float = Field(default=0.5, ge=0, le=1)
    task_success: bool = False
    speed_score: float = Field(default=0.5, ge=0, le=1)
    user_feedback: float = Field(default=0.5, ge=0, le=1)
    tool_efficiency: float = Field(default=0.5, ge=0, le=1)
    error_penalty: float = Field(default=0.0, ge=0, le=1)


class PlanRequest(BaseModel):
    task: str
    approved: bool = False


class SimulationRequest(BaseModel):
    tasks: list[str] = DEFAULT_SIMULATION_TASKS
    approved: bool = False


class SkillGenerateRequest(BaseModel):
    task_family: str


class SkillPromoteRequest(BaseModel):
    skill_id: str


class SkillOptimizeRequest(BaseModel):
    skill_id: str
    success: bool
    latency_seconds: float = 0.0
    tool_failures: int = 0
    feedback_score: float = Field(default=0.5, ge=0, le=1)


class FailureLessonRequest(BaseModel):
    task: str
    failure: str
    cause: str
    fix: str
    confidence: float = Field(default=0.7, ge=0, le=1)
    source: str = "manual"


class ToolRegisterRequest(BaseModel):
    name: str
    kind: str
    capabilities: list[str]
    requires_approval: bool = False
    risk_level: str = "low"
    enabled: bool = True


class ToolPlanRequest(BaseModel):
    task: str
    required_tools: list[str] = []
    approved: bool = False


class WorldNodeRequest(BaseModel):
    node_type: str
    name: str
    attributes: dict[str, Any] = {}
    confidence: float = Field(default=0.7, ge=0, le=1)


class WorldEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    relationship: str
    attributes: dict[str, Any] = {}
    confidence: float = Field(default=0.7, ge=0, le=1)


class PredictRequest(BaseModel):
    task: str


class DigitalTwinObserveRequest(BaseModel):
    task: str
    owner: str = "Yogesh"


class FutureSimulationRequest(BaseModel):
    prompt: str
    scenarios: list[str] = Field(default_factory=list)
    owner: str = "Yogesh"
    context: dict[str, Any] = Field(default_factory=dict)


class PredictiveRecommendationRequest(BaseModel):
    task: str
    owner: str = "Yogesh"


class MultimodalIngestRequest(BaseModel):
    session_id: str = "default"
    modality: str
    content_ref: str = ""
    summary: str = ""
    metadata: dict[str, Any] = {}
    confidence: float = Field(default=0.7, ge=0, le=1)


class BackgroundJobRequest(BaseModel):
    name: str
    kind: str
    payload: dict[str, Any] = {}
    schedule: dict[str, Any] = {}
    next_run_at: str | None = None
    max_runs: int = Field(default=1, ge=1, le=100)


class MarketplaceInstallRequest(BaseModel):
    manifest: dict[str, Any]


class MarketplaceUpdateRequest(BaseModel):
    name: str
    manifest: dict[str, Any]


class MarketplaceRemoveRequest(BaseModel):
    name: str


class GoalCreateRequest(BaseModel):
    title: str
    goal_context: str = ""
    goal_type: str = "project"
    goal_owner: str = "Yogesh"
    priority: float = Field(default=0.75, ge=0, le=1)
    deadline: str | None = None


class GoalStatusRequest(BaseModel):
    status: str
    blocked_reason: str = ""


class GoalDependencyRequest(BaseModel):
    depends_on_goal_id: str
    dependency_type: str = "blocks_until_complete"
    confidence: float = Field(default=0.8, ge=0, le=1)


class GoalTaskStatusRequest(BaseModel):
    status: str


class OpportunityScanRequest(BaseModel):
    signals: list[str | dict[str, Any]]
    goal_id: str | None = None


class DecisionSimulationRequest(BaseModel):
    decision: str
    choices: list[str]
    context: dict[str, Any] = {}


class GoalDecisionSimulationRequest(BaseModel):
    decision: str
    choices: list[str]


class PersonalOSItemRequest(BaseModel):
    item_type: str
    title: str
    content: str
    attributes: dict[str, Any] = {}
    confidence: float = Field(default=0.74, ge=0, le=1)


class PersonalOSClassifyRequest(BaseModel):
    text: str
    attributes: dict[str, Any] = {}
    confidence: float = Field(default=0.74, ge=0, le=1)


class EvolutionOptimizeRequest(BaseModel):
    task: str = ""
    runtime_metrics: dict[str, Any] = {}


class EvolutionPromoteRequest(BaseModel):
    event_id: str


class ReplayRecordRequest(BaseModel):
    replay_type: str
    reference_id: str
    payload: dict[str, Any]
    confidence: float = Field(default=0.75, ge=0, le=1)


class ExperimentRunRequest(BaseModel):
    name: str
    task: str
    variants: list[dict[str, Any]]
    metric_weights: dict[str, float] = {}


class KnowledgeEntityRequest(BaseModel):
    entity_type: str
    name: str
    attributes: dict[str, Any] = {}
    confidence: float = Field(default=0.75, ge=0, le=1)


class KnowledgeLinkRequest(BaseModel):
    source_id: str
    target_id: str
    relationship: str
    attributes: dict[str, Any] = {}
    confidence: float = Field(default=0.75, ge=0, le=1)


class KnowledgeIngestRequest(BaseModel):
    payload: dict[str, Any]


class AutonomousTestPlanRequest(BaseModel):
    scope: str
    changed_files: list[str] = []
    task: str = ""


class AutonomousTestReportRequest(BaseModel):
    scope: str
    test_plan: dict[str, Any]
    command: str
    status: str
    output_summary: str
    regressions: list[str] = []
    performance_score: float | None = Field(default=None, ge=0, le=1)


class AutonomousTestCompareRequest(BaseModel):
    previous_report_id: str
    current_report_id: str


class CommercePlanRequest(BaseModel):
    user_intent: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    owner: str = "Yogesh"
    approved: bool = False


class BookingPlanRequest(BaseModel):
    user_intent: str
    options: list[dict[str, Any]] = Field(default_factory=list)
    approved: bool = False


class VerificationActionRequest(BaseModel):
    action_type: str
    action_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    irreversible: bool | None = None


class LifeAutomationPlanRequest(BaseModel):
    user_intent: str
    signals: list[str | dict[str, Any]] = Field(default_factory=list)
    approved: bool = False


class BuyingPreferenceRequest(BaseModel):
    owner: str = "Yogesh"
    preferences: dict[str, Any] = Field(default_factory=dict)


class ConciergePlanRequest(BaseModel):
    user_intent: str
    approved: bool = False


class ExecutionBusPlanRequest(BaseModel):
    request_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False


class CollaborationResolveRequest(BaseModel):
    user_input: str


@router.get("/health")
def cognitive_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "layers": [
            "input_understanding",
            "memory",
            "learning",
            "skills",
            "agents",
            "planning",
            "safety",
            "cognitive_compression",
            "universal_tools",
            "world_model",
            "predictive_assistant",
            "adaptive_ui",
            "multimodal_context",
            "workflow_generation",
            "background_jobs",
            "skill_marketplace",
            "goal_graph",
            "autonomous_project_manager",
            "opportunity_detection",
            "decision_simulation",
            "personal_operating_system",
            "digital_executive_brain",
            "cognitive_observatory",
            "self_evolution",
            "explainable_ai",
            "time_machine_replay",
            "ai_experiment_lab",
            "adaptive_work_modes",
            "knowledge_graph",
            "autonomous_testing",
            "autonomous_action_platform",
            "commerce_engine",
            "booking_engine",
            "verification_recheck",
            "life_automation",
            "digital_concierge",
            "multi_service_execution_bus",
            "universal_autonomous_execution",
            "uncertainty_human_collaboration",
            "self_healing",
            "proactive_events",
            "universal_automation_layer",
            "cognitive_health",
            "cognitive_digital_twin",
            "future_simulation",
            "predictive_recommendations",
        ],
        "agent_limit": 10,
        "persistent_core_agents": 9,
        "temporary_worker_limit": 6,
        "recall_limit": 10,
    }


@router.post("/memory/short-term")
def add_short_term_memory(request: ShortTermRequest) -> dict[str, Any]:
    memory_id = _os.short_term.add(
        request.session_id,
        request.conversation,
        request.tool_usage,
        request.context_score,
    )
    return {"id": memory_id, "status": "stored"}


@router.post("/memory/long-term")
def add_long_term_memory(request: MemoryCreateRequest) -> dict[str, Any]:
    try:
        return _os.long_term.upsert(
            request.category,
            request.content,
            request.importance_score,
            request.source,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/memory/recall")
def recall_memory(request: RecallRequest) -> dict[str, Any]:
    return {"memories": _os.retrieval.recall(request.query, request.limit)}


@router.post("/memory/compress")
def compress_memory() -> dict[str, Any]:
    return _os.compression.compress()


@router.post("/memory/cognitive-compress")
def cognitive_compress_memory() -> dict[str, Any]:
    return _os.cognitive_compression.compress_context()


@router.get("/memory/cognitive-compress/latest")
def latest_cognitive_compression() -> dict[str, Any]:
    latest = _os.cognitive_compression.latest()
    return {"compression": latest}


@router.post("/experience")
def record_experience(request: ExperienceRequest) -> dict[str, Any]:
    try:
        experience = _os.experiences.record(request.dict())
        reflection = _os.reflection.reflect(experience["experience_id"])
        return {"experience": experience, "reflection": reflection}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/skills/generate")
def generate_skill(request: SkillGenerateRequest) -> dict[str, Any]:
    skill = _os.skill_generator.generate_from_repetitions(request.task_family)
    return {"generated": bool(skill), "skill": skill}


@router.post("/skills/promote")
def promote_skill(request: SkillPromoteRequest) -> dict[str, Any]:
    try:
        return _os.skills.promote(request.skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/skills/optimize")
def optimize_skill(request: SkillOptimizeRequest) -> dict[str, Any]:
    try:
        return _os.skill_optimizer.improve_after_use(
            request.skill_id,
            request.success,
            request.latency_seconds,
            request.tool_failures,
            request.feedback_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/skills/search")
def search_skills(q: str, limit: int = 10) -> dict[str, Any]:
    return {"skills": _os.skills.search(q, limit)}


@router.post("/plan")
def plan_task(request: PlanRequest) -> dict[str, Any]:
    return _os.process_task(request.task, approved=request.approved)


@router.post("/analyze")
def analyze_task(request: PlanRequest) -> dict[str, Any]:
    analysis = _os.task_analyzer.analyze(request.task).to_dict()
    return {"analysis": analysis, "hiring_plan": _os.hiring_engine.hiring_plan(analysis)}


@router.post("/simulate")
def simulate_tasks(request: SimulationRequest) -> dict[str, Any]:
    return {"results": HermesSimulator(_os).run(request.tasks, approved=request.approved)}


@router.get("/failures")
def recent_failures(limit: int = 10) -> dict[str, Any]:
    return _os.failures.recommendations(limit)


@router.post("/failures/lesson")
def record_failure_lesson(request: FailureLessonRequest) -> dict[str, Any]:
    try:
        return _os.failures.record_lesson(
            request.task,
            request.failure,
            request.cause,
            request.fix,
            request.confidence,
            request.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tools/register")
def register_tool(request: ToolRegisterRequest) -> dict[str, Any]:
    try:
        return _os.tools.register_tool(
            ToolSpec(
                name=request.name,
                kind=request.kind,
                capabilities=request.capabilities,
                requires_approval=request.requires_approval,
                risk_level=request.risk_level,
                enabled=request.enabled,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tools")
def list_tools(enabled_only: bool = True) -> dict[str, Any]:
    return {"tools": _os.tools.list_tools(enabled_only=enabled_only)}


@router.post("/tools/plan")
def plan_tools(request: ToolPlanRequest) -> dict[str, Any]:
    return _os.tools.plan_for_task(request.task, request.required_tools, request.approved)


@router.post("/world/node")
def upsert_world_node(request: WorldNodeRequest) -> dict[str, Any]:
    try:
        return _os.world_model.upsert_node(
            request.node_type,
            request.name,
            request.attributes,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/world/edge")
def add_world_edge(request: WorldEdgeRequest) -> dict[str, Any]:
    try:
        return _os.world_model.add_edge(
            request.source_id,
            request.target_id,
            request.relationship,
            request.attributes,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/world")
def world_graph(limit: int = 100) -> dict[str, Any]:
    return _os.world_model.graph(limit=limit)


@router.post("/predict")
def predict_next_actions(request: PredictRequest) -> dict[str, Any]:
    analysis = _os.task_analyzer.analyze(request.task).to_dict()
    return _os.predictive.predict(request.task, analysis)


@router.post("/digital-twin/observe")
def observe_digital_twin(request: DigitalTwinObserveRequest) -> dict[str, Any]:
    analysis = _os.task_analyzer.analyze(request.task).to_dict()
    return _os.digital_twin.observe_task(request.task, analysis, owner=request.owner)


@router.get("/digital-twin/profile")
def digital_twin_profile(owner: str = "Yogesh") -> dict[str, Any]:
    return _os.digital_twin.profile(owner)


@router.get("/digital-twin/signals")
def digital_twin_signals(owner: str = "Yogesh", signal_type: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"signals": _os.digital_twin.signals(owner=owner, signal_type=signal_type, limit=limit)}


@router.post("/future-simulations")
def future_simulation(request: FutureSimulationRequest) -> dict[str, Any]:
    return _os.future_simulation.simulate(
        request.prompt,
        scenarios=request.scenarios or None,
        owner=request.owner,
        context=request.context,
    )


@router.get("/future-simulations")
def future_simulations(owner: str | None = None, limit: int = 20) -> dict[str, Any]:
    return {"simulations": _os.future_simulation.latest(owner=owner, limit=limit)}


@router.post("/predictive-recommendations")
def predictive_recommendations(request: PredictiveRecommendationRequest) -> dict[str, Any]:
    analysis = _os.task_analyzer.analyze(request.task).to_dict()
    twin = _os.digital_twin.observe_task(request.task, analysis, owner=request.owner)
    simulation = _os.future_simulation.simulate(
        request.task,
        owner=request.owner,
        context={"analysis": analysis, "complexity_score": analysis["complexity_score"]},
    )
    return _os.predictive_recommendations.recommend(request.task, twin["profile"], simulation, analysis, owner=request.owner)


@router.get("/predictive-recommendations")
def predictive_recommendation_list(owner: str | None = None, limit: int = 20) -> dict[str, Any]:
    return {"recommendations": _os.predictive_recommendations.latest(owner=owner, limit=limit)}


@router.post("/ui/mode")
def adaptive_ui_mode(request: PredictRequest) -> dict[str, Any]:
    analysis = _os.task_analyzer.analyze(request.task).to_dict()
    return _os.adaptive_ui.mode_for_task(request.task, analysis)


@router.post("/multimodal/ingest")
def ingest_multimodal_context(request: MultimodalIngestRequest) -> dict[str, Any]:
    try:
        return _os.multimodal.ingest(
            request.session_id,
            request.modality,
            request.content_ref,
            request.summary,
            request.metadata,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/multimodal/session/{session_id}")
def multimodal_session_context(session_id: str, limit: int = 20) -> dict[str, Any]:
    return _os.multimodal.session_context(session_id, limit=limit)


@router.post("/workflows/generate")
def generate_workflow(request: PredictRequest) -> dict[str, Any]:
    return _os.workflow_generator.generate(request.task)


@router.post("/background/jobs")
def schedule_background_job(request: BackgroundJobRequest) -> dict[str, Any]:
    try:
        return _os.background_jobs.schedule(
            request.name,
            request.kind,
            request.payload,
            request.schedule,
            request.next_run_at,
            request.max_runs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/background/jobs")
def list_background_jobs(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"jobs": _os.background_jobs.list_jobs(status=status, limit=limit)}


@router.post("/background/jobs/run-due")
def run_due_background_jobs() -> dict[str, Any]:
    return _os.background_jobs.run_due()


@router.post("/marketplace/install")
def marketplace_install(request: MarketplaceInstallRequest) -> dict[str, Any]:
    try:
        return _os.marketplace.install(request.manifest)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/marketplace/update")
def marketplace_update(request: MarketplaceUpdateRequest) -> dict[str, Any]:
    try:
        return _os.marketplace.update(request.name, request.manifest)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/marketplace/remove")
def marketplace_remove(request: MarketplaceRemoveRequest) -> dict[str, Any]:
    return _os.marketplace.remove(request.name)


@router.get("/marketplace")
def marketplace_list(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"packages": _os.marketplace.list_packages(status=status, limit=limit)}


@router.post("/goals")
def create_goal(request: GoalCreateRequest) -> dict[str, Any]:
    try:
        return _os.executive_brain.intake_goal(
            title=request.title,
            goal_context=request.goal_context,
            goal_type=request.goal_type,
            goal_owner=request.goal_owner,
            priority=request.priority,
            deadline=request.deadline,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/goals")
def list_goals(owner: str | None = None, status: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"goals": _os.goal_graph.list_goals(owner=owner, status=status, limit=limit)}


@router.get("/goals/{goal_id}")
def goal_details(goal_id: str) -> dict[str, Any]:
    try:
        return _os.goal_graph.details(goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/goals/{goal_id}/decompose")
def decompose_goal(goal_id: str) -> dict[str, Any]:
    try:
        return _os.goal_graph.decompose_goal(goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/goals/{goal_id}/status")
def update_goal_status(goal_id: str, request: GoalStatusRequest) -> dict[str, Any]:
    try:
        return _os.goal_graph.update_goal_status(goal_id, request.status, request.blocked_reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/goals/{goal_id}/dependencies")
def add_goal_dependency(goal_id: str, request: GoalDependencyRequest) -> dict[str, Any]:
    try:
        return _os.goal_graph.add_dependency(
            goal_id,
            request.depends_on_goal_id,
            request.dependency_type,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/goals/{goal_id}/project-plan")
def create_goal_project_plan(goal_id: str) -> dict[str, Any]:
    try:
        return _os.project_manager.create_execution_plan(goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/goals/{goal_id}/progress")
def goal_progress(goal_id: str) -> dict[str, Any]:
    try:
        return _os.project_manager.progress_report(goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/goal-tasks/{task_id}/status")
def update_goal_task_status(task_id: str, request: GoalTaskStatusRequest) -> dict[str, Any]:
    try:
        return _os.project_manager.update_task_status(task_id, request.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/opportunities/detect")
def detect_opportunities(request: OpportunityScanRequest) -> dict[str, Any]:
    return _os.opportunities.detect(request.signals, goal_id=request.goal_id)


@router.get("/opportunities")
def list_opportunities(goal_id: str | None = None, status: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"opportunities": _os.opportunities.list_opportunities(goal_id=goal_id, status=status, limit=limit)}


@router.post("/decisions/simulate")
def simulate_decision(request: DecisionSimulationRequest) -> dict[str, Any]:
    try:
        return _os.decisions.simulate(request.decision, request.choices, request.context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/goals/{goal_id}/decisions/simulate")
def simulate_goal_decision(goal_id: str, request: GoalDecisionSimulationRequest) -> dict[str, Any]:
    try:
        return _os.executive_brain.simulate_decision_for_goal(goal_id, request.decision, request.choices)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/personal-os/items")
def create_personal_os_item(request: PersonalOSItemRequest) -> dict[str, Any]:
    try:
        return _os.personal_os.store_item(
            request.item_type,
            request.title,
            request.content,
            request.attributes,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/personal-os/classify")
def classify_personal_os_item(request: PersonalOSClassifyRequest) -> dict[str, Any]:
    try:
        return _os.personal_os.classify_and_store(request.text, request.attributes, request.confidence)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/personal-os/items")
def list_personal_os_items(item_type: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"items": _os.personal_os.list_items(item_type=item_type, limit=limit)}


@router.get("/personal-os/context")
def personal_os_context(q: str, limit: int = 10) -> dict[str, Any]:
    return _os.personal_os.context_bundle(q, limit=limit)


@router.post("/commerce/plan")
def commerce_plan(request: CommercePlanRequest) -> dict[str, Any]:
    return _os.commerce.plan(
        request.user_intent,
        candidates=request.candidates,
        owner=request.owner,
        approved=request.approved,
    )


@router.get("/commerce/requests")
def commerce_requests(limit: int = 50) -> dict[str, Any]:
    return {"requests": _os.commerce.list_requests(limit=limit)}


@router.post("/booking/plan")
def booking_plan(request: BookingPlanRequest) -> dict[str, Any]:
    return _os.booking.plan(request.user_intent, options=request.options, approved=request.approved)


@router.get("/booking/requests")
def booking_requests(limit: int = 50) -> dict[str, Any]:
    return {"requests": _os.booking.list_requests(limit=limit)}


@router.post("/verify/action")
def verify_action(request: VerificationActionRequest) -> dict[str, Any]:
    return _os.verification_recheck.verify(
        request.action_type,
        request.action_id,
        request.payload,
        approved=request.approved,
        irreversible=request.irreversible,
    )


@router.get("/verify/audits")
def verification_audits(limit: int = 50) -> dict[str, Any]:
    return {"audits": _os.verification_recheck.audits(limit=limit)}


@router.post("/life-automation/plan")
def life_automation_plan(request: LifeAutomationPlanRequest) -> dict[str, Any]:
    return _os.life_automation.plan(request.user_intent, signals=request.signals, approved=request.approved)


@router.get("/life-automation/plans")
def life_automation_plans(limit: int = 50) -> dict[str, Any]:
    return {"plans": _os.life_automation.list_plans(limit=limit)}


@router.get("/buying-intelligence/profile")
def buying_intelligence_profile(owner: str = "Yogesh") -> dict[str, Any]:
    return _os.buying_intelligence.profile(owner=owner)


@router.post("/buying-intelligence/preferences")
def update_buying_preferences(request: BuyingPreferenceRequest) -> dict[str, Any]:
    return _os.buying_intelligence.update_preferences(request.owner, request.preferences)


@router.post("/concierge/plan")
def concierge_plan(request: ConciergePlanRequest) -> dict[str, Any]:
    return _os.concierge.plan(request.user_intent, approved=request.approved)


@router.get("/concierge/plans")
def concierge_plans(limit: int = 50) -> dict[str, Any]:
    return {"plans": _os.concierge.list_plans(limit=limit)}


@router.post("/execution-bus/plan")
def execution_bus_plan(request: ExecutionBusPlanRequest) -> dict[str, Any]:
    return _os.execution_bus.plan(request.request_type, request.payload, approved=request.approved)


@router.get("/execution-bus/events")
def execution_bus_events(limit: int = 50) -> dict[str, Any]:
    return {"events": _os.execution_bus.events(limit=limit)}


@router.get("/action-platform/metrics")
def action_platform_metrics() -> dict[str, Any]:
    return _os.action_metrics.snapshot()


@router.get("/universal-execution/recent")
def universal_execution_recent(limit: int = 20) -> dict[str, Any]:
    return {"executions": _os.universal_execution.recent(limit=limit)}


@router.get("/collaboration/pending")
def collaboration_pending(limit: int = 20) -> dict[str, Any]:
    return {"questions": _os.uncertainty_collaboration.pending(limit=limit)}


@router.post("/collaboration/{question_id}/resolve")
def collaboration_resolve(question_id: str, request: CollaborationResolveRequest) -> dict[str, Any]:
    try:
        return _os.uncertainty_collaboration.resolve(question_id, request.user_input)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/self-healing/recent")
def self_healing_recent(limit: int = 20) -> dict[str, Any]:
    return {"events": _os.self_healing.recent(limit=limit)}


@router.get("/proactive-events")
def proactive_events(limit: int = 20) -> dict[str, Any]:
    return {"events": _os.proactive_events.recent(limit=limit)}


@router.get("/automation/plans")
def universal_automation_plans(limit: int = 20) -> dict[str, Any]:
    return {"plans": _os.universal_automation.recent(limit=limit)}


@router.get("/cognitive-health/latest")
def cognitive_health_latest(limit: int = 10) -> dict[str, Any]:
    return {"snapshots": _os.cognitive_health.latest(limit=limit)}


@router.get("/observatory/snapshot")
def observatory_snapshot() -> dict[str, Any]:
    return _os.observatory.snapshot(_os.metrics.snapshot())


@router.get("/observatory/history")
def observatory_history(limit: int = 10) -> dict[str, Any]:
    return {"snapshots": _os.observatory.latest(limit=limit)}


@router.post("/evolution/optimize")
def optimize_self_evolution(request: EvolutionOptimizeRequest) -> dict[str, Any]:
    return _os.self_evolution.optimize(request.task, request.runtime_metrics)


@router.post("/evolution/promote")
def promote_self_evolution(request: EvolutionPromoteRequest) -> dict[str, Any]:
    try:
        return _os.self_evolution.promote(request.event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evolution/events")
def list_self_evolution_events(status: str | None = None, limit: int = 20) -> dict[str, Any]:
    return {"events": _os.self_evolution.list_events(status=status, limit=limit)}


@router.get("/explainability/actions")
def list_action_explanations(limit: int = 20) -> dict[str, Any]:
    return {"explanations": _os.explainability.list_explanations(limit=limit)}


@router.post("/replay/record")
def record_replay_event(request: ReplayRecordRequest) -> dict[str, Any]:
    try:
        return _os.replay.record(request.replay_type, request.reference_id, request.payload, request.confidence)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/replay")
def replay_history(replay_type: str | None = None, reference_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    return _os.replay.replay(replay_type=replay_type, reference_id=reference_id, limit=limit)


@router.get("/replay/task")
def replay_task(task: str, limit: int = 20) -> dict[str, Any]:
    return _os.replay.replay_task(task, limit=limit)


@router.post("/experiments/run")
def run_experiment(request: ExperimentRunRequest) -> dict[str, Any]:
    try:
        return _os.experiments.run_experiment(
            request.name,
            request.task,
            request.variants,
            request.metric_weights or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/experiments")
def list_experiments(limit: int = 20) -> dict[str, Any]:
    return {"experiments": _os.experiments.list_experiments(limit=limit)}


@router.post("/knowledge/entities")
def upsert_knowledge_entity(request: KnowledgeEntityRequest) -> dict[str, Any]:
    try:
        return _os.knowledge_graph.upsert_entity(
            request.entity_type,
            request.name,
            request.attributes,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge/links")
def link_knowledge_entities(request: KnowledgeLinkRequest) -> dict[str, Any]:
    try:
        return _os.knowledge_graph.link(
            request.source_id,
            request.target_id,
            request.relationship,
            request.attributes,
            request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge/ingest")
def ingest_knowledge(request: KnowledgeIngestRequest) -> dict[str, Any]:
    return _os.knowledge_graph.ingest_goal_skill_user(request.payload)


@router.get("/knowledge/graph")
def knowledge_graph(limit: int = 100) -> dict[str, Any]:
    return _os.knowledge_graph.graph(limit=limit)


@router.post("/testing/plan")
def autonomous_test_plan(request: AutonomousTestPlanRequest) -> dict[str, Any]:
    return _os.autonomous_testing.generate_test_plan(request.scope, request.changed_files, request.task)


@router.post("/testing/report")
def autonomous_test_report(request: AutonomousTestReportRequest) -> dict[str, Any]:
    try:
        return _os.autonomous_testing.record_report(
            request.scope,
            request.test_plan,
            request.command,
            request.status,
            request.output_summary,
            request.regressions,
            request.performance_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/testing/compare")
def autonomous_test_compare(request: AutonomousTestCompareRequest) -> dict[str, Any]:
    try:
        return _os.autonomous_testing.compare_results(request.previous_report_id, request.current_report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/testing/reports")
def autonomous_test_reports(scope: str | None = None, limit: int = 20) -> dict[str, Any]:
    return {"reports": _os.autonomous_testing.reports(scope=scope, limit=limit)}


@router.get("/metrics")
def cognitive_metrics() -> dict[str, Any]:
    return _os.metrics.snapshot()


@router.post("/loop/run-once")
async def run_learning_maintenance() -> dict[str, Any]:
    loop = ContinuousLearningLoop(_os.store)
    return await loop.run_once()
