from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field
from zentex.web_console.contracts.llm_trace import LLMTracePayload




class NineQuestionsReportPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    session_id: str
    status: str = "ready"
    status_message: str | None = None
    last_turn_id: str
    snapshot_version: int = 0
    revision: int = 0
    refreshed_at: str | None = None
    last_refresh_reason: str | None = None
    question_driver_refs: list[str] = Field(default_factory=list)
    questions: list[NineQuestionReportItem] = Field(default_factory=list)
    trace_ids: dict[str, str] = Field(default_factory=dict)


class NineQuestionSandboxRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    mock_context: dict[str, Any] = Field(default_factory=dict)


class NineQuestionsRunRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    force_refresh: bool = True


class NineQuestionsRunResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    started: bool
    trace_id: str
    refresh_reason: str
    snapshot_version: int = 0
    revision: int = 0


class Q1StructureTreeRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    row_id: str
    path: str
    label: str
    depth: int = 0
    kind: str = "directory"
    file_count: int | None = None
    summary: str | None = None


class Q1CandidateGroupDetail(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    group_id: str
    label: str
    file_count: int | None = None
    summary: str | None = None


class Q1RiskFileDetail(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    path: str
    severity: str | None = None
    reason: str | None = None


class Q1WorkspaceSampleSummary(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    path: str | None = None
    file: str | None = None
    title: str | None = None
    header: str | None = None
    summary: str | None = None
    snippet: str | None = None
    excerpt: str | None = None
    first_lines: str | None = None


class Q1LongTextEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    evidence_id: str
    label: str
    kind: str
    source: str
    path: str | None = None
    text: str


class Q1PhysicalAndEnvironmentEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    environment_event: dict[str, Any] = Field(default_factory=dict)
    physical_host_state: dict[str, Any] = Field(default_factory=dict)
    memory_pressure: str | None = None
    network_health: str | None = None
    memory_pressure_status: str = "unknown"
    network_health_status: str = "unknown"
    environment_summary: list[str] = Field(default_factory=list)


class Q1WorkspaceStructureEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    directory_hierarchy_summary: str | None = None
    top_level_dirs: list[str] = Field(default_factory=list)
    file_total_count: int | None = None
    suffix_distribution: dict[str, int] = Field(default_factory=dict)
    high_frequency_filename_keywords: dict[str, int] = Field(default_factory=dict)
    candidate_groups: list[str] = Field(default_factory=list)
    obvious_risk_files: list[str] = Field(default_factory=list)
    directory_tree_rows: list[Q1StructureTreeRow] = Field(default_factory=list)
    candidate_group_details: list[Q1CandidateGroupDetail] = Field(default_factory=list)
    obvious_risk_file_details: list[Q1RiskFileDetail] = Field(default_factory=list)
    analyzer_snapshot: dict[str, Any] = Field(default_factory=dict)


class Q1WorkspaceContentSamplingEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    sampled_file_summaries: list[Q1WorkspaceSampleSummary] = Field(default_factory=list)
    log_anomaly_snippets: list[str] = Field(default_factory=list)
    long_text_evidence: list[Q1LongTextEvidence] = Field(default_factory=list)
    sample_count: int = 0
    anomaly_count: int = 0
    sampler_snapshot: dict[str, Any] = Field(default_factory=dict)


class Q1PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    physical_and_environment: Q1PhysicalAndEnvironmentEvidence
    workspace_structure: Q1WorkspaceStructureEvidence
    workspace_content_sampling: Q1WorkspaceContentSamplingEvidence


class WorkspaceDomainInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    primary_domain: str
    secondary_domains: list[str] = Field(default_factory=list)
    confidence: float
    reasoning_summary: str
    uncertainties: list[str] = Field(default_factory=list)
    suggested_first_step: str


class Q1LLMUpgradeProfileView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    program_id: str
    target_component: str
    baseline_version: str
    target_metric: str
    objective_summary: str
    dataset_refs: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)


class Q1LLMUpgradeView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    planning_status: str
    profile: Q1LLMUpgradeProfileView
    candidate_version: str | None = None
    release_gate: list[str] = Field(default_factory=list)
    error_message: str | None = None


class Q2Q1Summary(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    primary_domain: str
    secondary_domains: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    risk_summary: str | None = None


class Q2IdentityKernel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    meta_motivation: str
    values_prohibition: str
    non_bypassable_constraints: list[str] = Field(default_factory=list)


class Q2ManualIntervention(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    latest_manual_role_modification: str | None = None
    applied_at: str | None = None


class Q2PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    q1_summary: Q2Q1Summary
    identity_kernel: Q2IdentityKernel
    manual_intervention: Q2ManualIntervention | None = None


class Q2RoleView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    identity_role: str
    active_role: str
    task_role: str


class Q2MissionBoundaryView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    current_mission: str
    priority_duties: list[str] = Field(default_factory=list)
    continuity_boundaries: list[str] = Field(default_factory=list)


class Q2WhoAmIInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    role_profile: Q2RoleView
    mission_boundary: Q2MissionBoundaryView


class Q3WorkspaceAndPermission(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    workspaces: list[str] = Field(default_factory=list)
    tenant_permissions: list[str] = Field(default_factory=list)
    execution_tokens: list[str] = Field(default_factory=list)


class Q3AssetRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    id: str
    name: str
    introduction: str
    function_description: str


class Q3AgentRow(Q3AssetRow):
    model_config = ConfigDict(extra="ignore", frozen=True)
    status: str | None = None


class Q3ToolsAndAgents(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    cognitive_tools: list[str] = Field(default_factory=list)
    execution_tools: list[str] = Field(default_factory=list)
    connected_agents: list[dict[str, Any]] = Field(default_factory=list)
    cognitive_tool_rows: list[Q3AssetRow] = Field(default_factory=list)
    execution_tool_rows: list[Q3AssetRow] = Field(default_factory=list)
    connected_agent_rows: list[Q3AgentRow] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list, description="MCP 服务器列表")
    cli_tools: list[dict[str, Any]] = Field(default_factory=list, description="CLI 工具列表")


class Q3MemoryAndStrategy(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    experience_logs: list[str] = Field(default_factory=list)
    strategy_patches: list[str] = Field(default_factory=list)


class Q3PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    workspace_permission: Q3WorkspaceAndPermission
    tools_agents: Q3ToolsAndAgents
    memory_strategy: Q3MemoryAndStrategy


class Q3ResourceSufficiencyView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    resource_status: str  # 充沛, 降级, 匮乏
    resource_status_label: str | None = None
    resource_status_explanation: str | None = None
    missing_critical_assets: list[str] = Field(default_factory=list)
    bottleneck_node: str | None = None
    reasoning_summary: str | None = None


class Q3WhatDoIHaveInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    sufficiency_assessment: Q3ResourceSufficiencyView


class Q4PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    q1_context: dict[str, Any] = Field(default_factory=dict)
    q2_context: dict[str, Any] = Field(default_factory=dict)
    q3_inventory: dict[str, Any] = Field(default_factory=dict)


class Q4WhatCanIDoInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    capability_upper_limits: list[str] = Field(default_factory=list)
    actionable_space: list[str] = Field(default_factory=list)
    executable_strategies: list[str] = Field(default_factory=list)


class Q5PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    actionable_space: list[str] = Field(default_factory=list)
    contact_policy: list[str] = Field(default_factory=list)
    tenant_boundaries: list[str] = Field(default_factory=list)
    agent_trust_status: dict[str, str] = Field(default_factory=dict)


class Q5WhatAmIAllowedToDoInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    execution_tier: str
    interaction_scope: str
    requires_human_confirmation: bool
    requires_cloud_audit: bool
    explicitly_forbidden_actions: list[str] = Field(default_factory=list)
    compliance_risks: list[str] = Field(default_factory=list)
    allowed_delegation_targets: list[str] = Field(default_factory=list)


class Q6PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    actionable_space: list[str] = Field(default_factory=list)
    authorization_boundaries: list[str] = Field(default_factory=list)
    non_bypassable_constraints: list[str] = Field(default_factory=list)
    historical_strategy_patches: list[str] = Field(default_factory=list)


class Q6ForbiddenZoneInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    absolute_red_lines: list[str] = Field(default_factory=list)
    performance_tradeoff_bans: list[str] = Field(default_factory=list)
    prohibited_strategies: list[str] = Field(default_factory=list)
    contamination_risks: list[str] = Field(default_factory=list)


class Q7PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    resource_bottlenecks: list[str] = Field(default_factory=list)
    capability_limits: list[str] = Field(default_factory=list)
    permission_boundaries: list[str] = Field(default_factory=list)
    absolute_red_lines: list[str] = Field(default_factory=list)
    historical_failure_patches: list[str] = Field(default_factory=list)


class Q7AlternativeStrategyInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    fallback_plans: list[str] = Field(default_factory=list)
    degradation_strategies: list[str] = Field(default_factory=list)
    collaboration_switches: list[str] = Field(default_factory=list)
    exploratory_actions: list[str] = Field(default_factory=list)


class Q8AggregatedContextEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    q1_to_q7_snapshot: dict[str, Any] = Field(default_factory=dict)
    absolute_red_line_count: int = 0
    capability_ceiling_count: int = 0


class Q8PersistentTaskItem(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    item_id: str
    title: str
    status: str
    priority: int | None = None
    blocker_reason: str | None = None


class Q8AgendaItem(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    item_id: str
    title: str
    status: str
    priority: int | None = None
    next_review_condition: str | None = None
    delay_risk_score: float | None = None


class Q8RuntimeStateEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    persistent_task_state: list[Q8PersistentTaskItem] = Field(default_factory=list)
    cognitive_agenda: list[Q8AgendaItem] = Field(default_factory=list)


class Q8PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    aggregated_context: Q8AggregatedContextEvidence
    runtime_state: Q8RuntimeStateEvidence


class Q8ObjectiveProfileView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    current_primary_objective: str
    current_phase_tasks: list[str] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)


class Q8AutonomousTaskQueueView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    next_self_tasks: list[dict[str, Any]] = Field(default_factory=list)
    blocked_self_tasks: list[dict[str, Any]] = Field(default_factory=list)
    proactive_actions: list[dict[str, Any]] = Field(default_factory=list)


class Q8WhatShouldIDoNowInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    objective_profile: Q8ObjectiveProfileView
    task_queue: Q8AutonomousTaskQueueView


class Q9CognitiveSnapshotEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    q1_to_q8_snapshot: dict[str, Any] = Field(default_factory=dict)
    uncertainty_count: int = 0
    absolute_red_line_count: int = 0


class Q9RecentWeaknessView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    pattern_id: str | None = None
    pattern_type: str
    frequency: int | None = None
    severity: str | None = None


class Q9SelfModelEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    cognitive_load: str
    stability_level: str | None = None
    confidence_drift: float | None = None
    recent_weaknesses: list[Q9RecentWeaknessView] = Field(default_factory=list)


class Q9ReasoningBudgetEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    compute_remaining_ratio: float = 0.0
    token_remaining_ratio: float = 0.0
    time_remaining_ratio: float = 0.0
    budget_pressure: str | None = None


class Q9PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    cognitive_snapshot: Q9CognitiveSnapshotEvidence
    self_model: Q9SelfModelEvidence
    reasoning_budget: Q9ReasoningBudgetEvidence


class Q9ActionPostureInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    evaluation_style: str
    risk_tolerance: str
    action_rhythm: str
    confirmation_strategy: str
    evolution_direction: str


class MountedPluginInfo(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    plugin_id: str
    display_name: str
    source_kind: str  # "base", "patch"
    version: str
    description: str
    function_description: str
    status: str  # "active", "candidate", "degraded", "revoked"


class NineQuestionReportItem(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str
    title: str
    tool_id: str
    summary: str
    confidence: float
    result: Any
    context_updates: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    timestamp: str
    cache_status: str = "未知"
    provider_name: str | None = None
    mounted_plugins: list[MountedPluginInfo] = Field(default_factory=list)
    preprocessed_evidence: Union[
        Q1PreprocessedEvidence,
        Q2PreprocessedEvidence,
        Q3PreprocessedEvidence,
        Q4PreprocessedEvidence,
        Q5PreprocessedEvidence,
        Q6PreprocessedEvidence,
        Q7PreprocessedEvidence,
        Q8PreprocessedEvidence,
        Q9PreprocessedEvidence,
        None,
    ] = None
    inference_result: Union[
        WorkspaceDomainInferenceView,
        Q2WhoAmIInferenceView,
        Q3WhatDoIHaveInferenceView,
        Q4WhatCanIDoInferenceView,
        Q5WhatAmIAllowedToDoInferenceView,
        Q6ForbiddenZoneInferenceView,
        Q7AlternativeStrategyInferenceView,
        Q8WhatShouldIDoNowInferenceView,
        Q9ActionPostureInferenceView,
        None,
    ] = None
    q1_llm_upgrade: Q1LLMUpgradeView | None = None
    llm_trace_payload: LLMTracePayload | None = None


class NineQuestionSandboxResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    question_id: str
    title: str
    tool_id: str
    summary: str
    confidence: float
    trace_id: str
    elapsed_ms: int
    provider_name: str | None = None
    mounted_plugins: list[MountedPluginInfo] = Field(default_factory=list)
    prompt: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    result: Any
    context_updates: dict[str, Any] = Field(default_factory=dict)
    preprocessed_evidence: Union[
        Q1PreprocessedEvidence,
        Q2PreprocessedEvidence,
        Q3PreprocessedEvidence,
        Q4PreprocessedEvidence,
        Q5PreprocessedEvidence,
        Q6PreprocessedEvidence,
        Q7PreprocessedEvidence,
        Q8PreprocessedEvidence,
        Q9PreprocessedEvidence,
        None,
    ] = None
    inference_result: Union[
        WorkspaceDomainInferenceView,
        Q2WhoAmIInferenceView,
        Q3WhatDoIHaveInferenceView,
        Q4WhatCanIDoInferenceView,
        Q5WhatAmIAllowedToDoInferenceView,
        Q6ForbiddenZoneInferenceView,
        Q7AlternativeStrategyInferenceView,
        Q8WhatShouldIDoNowInferenceView,
        Q9ActionPostureInferenceView,
        None,
    ] = None
    q1_llm_upgrade: Q1LLMUpgradeView | None = None
    llm_trace_payload: LLMTracePayload | None = None


NineQuestionReportItem.model_rebuild()
NineQuestionSandboxResponse.model_rebuild()
NineQuestionsReportPayload.model_rebuild()
