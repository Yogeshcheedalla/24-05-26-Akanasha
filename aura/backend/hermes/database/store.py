from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator


DATABASE_DIR = Path(__file__).resolve().parent
MEMORIES_DB = DATABASE_DIR / "memories.db"
SKILLS_DB = DATABASE_DIR / "skills.db"
EXPERIENCES_DB = DATABASE_DIR / "experiences.db"
AGENTS_DB = DATABASE_DIR / "agents.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def stable_fingerprint(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", normalize_text(value))
    return " ".join(normalized.split()[:80])


def token_embedding(value: str) -> dict[str, float]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", value.lower())
    counts = Counter(tokens)
    total = math.sqrt(sum(weight * weight for weight in counts.values())) or 1.0
    return {token: round(weight / total, 6) for token, weight in counts.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    keys = set(left) & set(right)
    return max(0.0, min(1.0, sum(left[key] * right[key] for key in keys)))


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str | None, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


@dataclass(frozen=True)
class DatabaseFiles:
    memories: Path = MEMORIES_DB
    skills: Path = SKILLS_DB
    experiences: Path = EXPERIENCES_DB
    agents: Path = AGENTS_DB


class CognitiveStore:
    """Small, durable SQLite store split by domain for rollback and safety.

    The store uses standard-library sqlite3 to keep the cognitive layer portable
    and independent from the existing Akansha application database.
    """

    def __init__(self, files: DatabaseFiles | None = None) -> None:
        self.files = files or DatabaseFiles()
        self._lock = RLock()
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self, db_path: Path) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def initialize(self) -> None:
        self._init_memories()
        self._init_skills()
        self._init_experiences()
        self._init_agents()
        self._init_operating_system()
        self._init_goal_engine()
        self._init_observability_engines()
        self._init_digital_twin()

    def _init_memories(self) -> None:
        with self.connect(self.files.memories) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    memory_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance_score REAL NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    last_accessed TEXT,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    embedding TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS short_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    conversation TEXT NOT NULL,
                    tool_usage TEXT NOT NULL,
                    context_score REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ltm_category ON long_term_memories(category);
                CREATE INDEX IF NOT EXISTS idx_stm_session ON short_term_memory(session_id, timestamp);
                CREATE TABLE IF NOT EXISTS cognitive_compressions (
                    id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    decisions TEXT NOT NULL,
                    user_patterns TEXT NOT NULL,
                    lessons TEXT NOT NULL,
                    archived_memory_ids TEXT NOT NULL,
                    removed_noise INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _init_skills(self) -> None:
        with self.connect(self.files.skills) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    trigger_conditions TEXT NOT NULL,
                    required_tools TEXT NOT NULL,
                    execution_steps TEXT NOT NULL,
                    examples TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    version INTEGER NOT NULL,
                    success_rate REAL NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    reward_score REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    parent_id TEXT,
                    rollback_id TEXT,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(name, version)
                );
                CREATE TABLE IF NOT EXISTS skill_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_marketplace (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    skill_id TEXT,
                    manifest TEXT NOT NULL,
                    rollback_id TEXT,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(name, version)
                );
                CREATE TABLE IF NOT EXISTS marketplace_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id TEXT,
                    skill_id TEXT,
                    action TEXT NOT NULL,
                    version INTEGER,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_skill_name ON skills(name);
                CREATE INDEX IF NOT EXISTS idx_skill_fingerprint ON skills(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_skill_marketplace_name ON skill_marketplace(name);
                """
            )

    def _init_experiences(self) -> None:
        with self.connect(self.files.experiences) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiences (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    actions_taken TEXT NOT NULL,
                    tools_used TEXT NOT NULL,
                    agents_used TEXT NOT NULL,
                    errors TEXT NOT NULL,
                    successful_steps TEXT NOT NULL,
                    time_taken REAL NOT NULL,
                    feedback TEXT NOT NULL,
                    score REAL NOT NULL,
                    reward REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reflections (
                    id TEXT PRIMARY KEY,
                    experience_id TEXT NOT NULL,
                    worked TEXT NOT NULL,
                    failed TEXT NOT NULL,
                    lessons TEXT NOT NULL,
                    candidate_skill TEXT,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS failure_lessons (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    failure TEXT NOT NULL,
                    cause TEXT NOT NULL,
                    fix TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_experience_task ON experiences(task);
                CREATE INDEX IF NOT EXISTS idx_failure_lessons_task ON failure_lessons(task);
                """
            )

    def _init_agents(self) -> None:
        with self.connect(self.files.agents) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL UNIQUE,
                    specialization TEXT NOT NULL,
                    goals TEXT NOT NULL,
                    tools TEXT NOT NULL,
                    memory_scope TEXT NOT NULL,
                    communication_protocol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_active TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    decomposition TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    required_agents TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _init_operating_system(self) -> None:
        with self.connect(self.files.agents) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tool_registry (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    capabilities TEXT NOT NULL,
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    risk_level TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS world_nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS world_edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    required_tools TEXT NOT NULL,
                    agent_types TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS background_jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    next_run_at TEXT,
                    last_run_at TEXT,
                    status TEXT NOT NULL,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    max_runs INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS multimodal_contexts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    content_ref TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_registry_kind ON tool_registry(kind);
                CREATE INDEX IF NOT EXISTS idx_world_nodes_type ON world_nodes(node_type);
                CREATE INDEX IF NOT EXISTS idx_world_edges_source ON world_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_intent ON workflow_templates(intent);
                CREATE INDEX IF NOT EXISTS idx_background_jobs_due ON background_jobs(status, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_multimodal_session ON multimodal_contexts(session_id, created_at);
                """
            )

    def _init_goal_engine(self) -> None:
        with self.connect(self.files.agents) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    goal_type TEXT NOT NULL,
                    goal_owner TEXT NOT NULL,
                    goal_context TEXT NOT NULL,
                    priority REAL NOT NULL,
                    deadline TEXT,
                    progress REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    estimated_effort REAL NOT NULL DEFAULT 0,
                    completion_score REAL NOT NULL DEFAULT 0,
                    goal_health TEXT NOT NULL DEFAULT 'healthy',
                    blocked_reason TEXT NOT NULL DEFAULT '',
                    risk_score REAL NOT NULL DEFAULT 0,
                    milestones TEXT NOT NULL DEFAULT '[]',
                    execution_state TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0.75,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS goal_dependencies (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    depends_on_goal_id TEXT NOT NULL,
                    dependency_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(goal_id, depends_on_goal_id),
                    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
                    FOREIGN KEY(depends_on_goal_id) REFERENCES goals(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS goal_tasks (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    parent_task_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    priority REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    estimated_effort REAL NOT NULL DEFAULT 1,
                    deadline TEXT,
                    dependency_ids TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.75,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS goal_milestones (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    due_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress REAL NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.75,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS goal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT,
                    source TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    priority REAL NOT NULL,
                    risk_score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decision_simulations (
                    id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    choices TEXT NOT NULL,
                    ranked_choices TEXT NOT NULL,
                    context TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS personal_os_items (
                    id TEXT PRIMARY KEY,
                    item_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_goals_owner ON goals(goal_owner, updated_at);
                CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status, priority);
                CREATE INDEX IF NOT EXISTS idx_goal_tasks_goal ON goal_tasks(goal_id, status);
                CREATE INDEX IF NOT EXISTS idx_goal_milestones_goal ON goal_milestones(goal_id, status);
                CREATE INDEX IF NOT EXISTS idx_opportunities_goal ON opportunities(goal_id, priority);
                CREATE INDEX IF NOT EXISTS idx_personal_os_type ON personal_os_items(item_type, updated_at);
                """
            )

    def _init_observability_engines(self) -> None:
        with self.connect(self.files.agents) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS observatory_snapshots (
                    id TEXT PRIMARY KEY,
                    snapshot TEXT NOT NULL,
                    health_score REAL NOT NULL,
                    token_usage INTEGER NOT NULL,
                    learning_progress REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS self_evolution_events (
                    id TEXT PRIMARY KEY,
                    area TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    before_state TEXT NOT NULL,
                    after_state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    metrics TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS action_explanations (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    workflow_selection TEXT NOT NULL,
                    agent_selection TEXT NOT NULL,
                    skill_selection TEXT NOT NULL,
                    tool_selection TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS replay_events (
                    id TEXT PRIMARY KEY,
                    replay_type TEXT NOT NULL,
                    reference_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    task TEXT NOT NULL,
                    variants TEXT NOT NULL,
                    status TEXT NOT NULL,
                    winner TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    variant_name TEXT NOT NULL,
                    variant_type TEXT NOT NULL,
                    score REAL NOT NULL,
                    metrics TEXT NOT NULL,
                    result TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS knowledge_graph_facts (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_graph_links (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS autonomous_test_reports (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    test_plan TEXT NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_summary TEXT NOT NULL,
                    regressions TEXT NOT NULL,
                    performance_score REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commerce_requests (
                    id TEXT PRIMARY KEY,
                    user_intent TEXT NOT NULL,
                    requirement_profile TEXT NOT NULL,
                    product_candidates TEXT NOT NULL,
                    ranked_recommendations TEXT NOT NULL,
                    verification TEXT NOT NULL,
                    approval_state TEXT NOT NULL,
                    execution_state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS booking_requests (
                    id TEXT PRIMARY KEY,
                    booking_type TEXT NOT NULL,
                    user_intent TEXT NOT NULL,
                    requirement_profile TEXT NOT NULL,
                    options TEXT NOT NULL,
                    ranked_recommendations TEXT NOT NULL,
                    schedule_validation TEXT NOT NULL,
                    conflict_analysis TEXT NOT NULL,
                    verification TEXT NOT NULL,
                    approval_state TEXT NOT NULL,
                    execution_state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS verification_audits (
                    id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    checks TEXT NOT NULL,
                    conflicts TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    irreversible INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS life_automation_plans (
                    id TEXT PRIMARY KEY,
                    automation_type TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    action_plan TEXT NOT NULL,
                    approval_state TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS buying_intelligence_profiles (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    preferences TEXT NOT NULL,
                    budget_patterns TEXT NOT NULL,
                    brand_preferences TEXT NOT NULL,
                    purchase_history TEXT NOT NULL,
                    risk_tolerance TEXT NOT NULL,
                    insights TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS concierge_plans (
                    id TEXT PRIMARY KEY,
                    concierge_type TEXT NOT NULL,
                    user_intent TEXT NOT NULL,
                    itinerary TEXT NOT NULL,
                    recommendations TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    verification TEXT NOT NULL,
                    approval_state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_bus_events (
                    id TEXT PRIMARY KEY,
                    request_type TEXT NOT NULL,
                    service_plan TEXT NOT NULL,
                    auth_requirements TEXT NOT NULL,
                    execution_steps TEXT NOT NULL,
                    monitoring TEXT NOT NULL,
                    approval_state TEXT NOT NULL,
                    result TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS action_platform_metrics (
                    id TEXT PRIMARY KEY,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    dimensions TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS universal_executions (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    execution_tree TEXT NOT NULL,
                    verification TEXT NOT NULL,
                    learning_update TEXT NOT NULL,
                    dashboard_update TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collaboration_questions (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    question TEXT NOT NULL,
                    context TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS self_healing_events (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    failure_type TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    recovery_plan TEXT NOT NULL,
                    validation TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proactive_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    priority REAL NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automation_plans (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    surfaces TEXT NOT NULL,
                    action_plan TEXT NOT NULL,
                    required_permissions TEXT NOT NULL,
                    approval_state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cognitive_health_snapshots (
                    id TEXT PRIMARY KEY,
                    system_health REAL NOT NULL,
                    prediction_confidence REAL NOT NULL,
                    memory_efficiency REAL NOT NULL,
                    agent_activity TEXT NOT NULL,
                    tool_failures TEXT NOT NULL,
                    execution_latency TEXT NOT NULL,
                    workflow_efficiency TEXT NOT NULL,
                    resource_consumption TEXT NOT NULL,
                    hallucination_signals TEXT NOT NULL,
                    learning_quality TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_observatory_created ON observatory_snapshots(created_at);
                CREATE INDEX IF NOT EXISTS idx_self_evolution_area ON self_evolution_events(area, status);
                CREATE INDEX IF NOT EXISTS idx_action_explanations_task ON action_explanations(task, created_at);
                CREATE INDEX IF NOT EXISTS idx_replay_reference ON replay_events(replay_type, reference_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_experiments_name ON experiments(name, created_at);
                CREATE INDEX IF NOT EXISTS idx_knowledge_facts_type ON knowledge_graph_facts(entity_type, name);
                CREATE INDEX IF NOT EXISTS idx_knowledge_links_source ON knowledge_graph_links(source_id, relationship);
                CREATE INDEX IF NOT EXISTS idx_autonomous_test_scope ON autonomous_test_reports(scope, created_at);
                CREATE INDEX IF NOT EXISTS idx_commerce_status ON commerce_requests(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_booking_type_status ON booking_requests(booking_type, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_verification_action ON verification_audits(action_type, action_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_life_automation_status ON life_automation_plans(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_buying_owner ON buying_intelligence_profiles(owner, updated_at);
                CREATE INDEX IF NOT EXISTS idx_concierge_type_status ON concierge_plans(concierge_type, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_execution_bus_type ON execution_bus_events(request_type, created_at);
                CREATE INDEX IF NOT EXISTS idx_action_metrics_name ON action_platform_metrics(metric_name, created_at);
                CREATE INDEX IF NOT EXISTS idx_universal_executions_intent ON universal_executions(intent, status, created_at);
                CREATE INDEX IF NOT EXISTS idx_collaboration_status ON collaboration_questions(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_self_healing_status ON self_healing_events(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_proactive_events_status ON proactive_events(status, priority);
                CREATE INDEX IF NOT EXISTS idx_automation_plans_status ON automation_plans(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_cognitive_health_created ON cognitive_health_snapshots(created_at);
                """
            )

    def _init_digital_twin(self) -> None:
        with self.connect(self.files.agents) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS digital_twin_signals (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 1,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS digital_twin_profiles (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    model_summary TEXT NOT NULL,
                    habits TEXT NOT NULL,
                    preferences TEXT NOT NULL,
                    goals TEXT NOT NULL,
                    projects TEXT NOT NULL,
                    learning_patterns TEXT NOT NULL,
                    work_patterns TEXT NOT NULL,
                    decision_history TEXT NOT NULL,
                    execution_history TEXT NOT NULL,
                    productivity_patterns TEXT NOT NULL,
                    behavior_trends TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS future_simulations (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    scenarios TEXT NOT NULL,
                    best_scenario TEXT NOT NULL,
                    risk_heatmap TEXT NOT NULL,
                    goal_forecast TEXT NOT NULL,
                    decision_comparison TEXT NOT NULL,
                    timeline_projection TEXT NOT NULL,
                    behavior_trends TEXT NOT NULL,
                    opportunity_prediction TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    context TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS predictive_recommendations (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    task TEXT NOT NULL,
                    proactive_actions TEXT NOT NULL,
                    risk_alerts TEXT NOT NULL,
                    optimization_suggestions TEXT NOT NULL,
                    goal_improvements TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source_simulation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_digital_twin_signals_owner ON digital_twin_signals(owner, signal_type, updated_at);
                CREATE INDEX IF NOT EXISTS idx_digital_twin_profiles_owner ON digital_twin_profiles(owner, updated_at);
                CREATE INDEX IF NOT EXISTS idx_future_simulations_owner ON future_simulations(owner, created_at);
                CREATE INDEX IF NOT EXISTS idx_predictive_recommendations_owner ON predictive_recommendations(owner, status, created_at);
                """
            )


_store: CognitiveStore | None = None


def get_cognitive_store() -> CognitiveStore:
    global _store
    if _store is None:
        _store = CognitiveStore()
    return _store
