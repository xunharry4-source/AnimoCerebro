
export interface TraceRelatedEvent {
  entry_id: string;
  entry_type: string;
  timestamp: string;
  trace_id: string;
  payload: any;
}

// Reflection types
export interface NineQuestionReflectionResultAnalysis {
  effective: boolean;
  effectiveness_score: number;
  need_upgrade: boolean;
  missing_data: string[];
}

export interface NineQuestionReflectionResult {
  question_id: string;
  status: string;
  created_at?: string;
  analysis: NineQuestionReflectionResultAnalysis;
  reflection_error?: string | null;
  score?: number | null;
  feedback?: string | null;
  suggestions?: string[];
}

export interface NineQuestionReflectionRecord {
  reflection_id: string;
  created_at: string;
  context: Record<string, any>;
  results?: NineQuestionReflectionResult[];
  [key: string]: any;
}

// Workflow types
export interface NineQuestionWorkflowEvent {
  entry_id?: string;
  timestamp: string;
  phase: string;
  phase_status: string;
  message: string;
  error_message?: string | null;
}

export interface NineQuestionWorkflowPhaseStatus {
  phase: string;
  status: string;
}

export interface NineQuestionWorkflowQuestionStatus {
  question_id: string;
  question_title: string;
  current_status: string;
  authenticity_status?: string | null;
  used_fallback?: boolean;
  latest_trace_id?: string | null;
  last_event_at?: string | null;
  latest_error?: string | null;
  trace_count: number;
  diagnosis_code: string;
  diagnosis_message: string;
  module_runs?: NineQuestionWorkflowModuleRun[];
  plugin_runs?: NineQuestionWorkflowPluginRun[];
  upstream_dependencies?: NineQuestionWorkflowDependency[];
  recovery_plan?: NineQuestionRecoveryPlan | null;
  phase_statuses: NineQuestionWorkflowPhaseStatus[];
  events: NineQuestionWorkflowEvent[];
}

export interface NineQuestionWorkflowPayload {
  questions: NineQuestionWorkflowQuestionStatus[];
  events: NineQuestionWorkflowEvent[];
  session_id?: string;
  event_count?: number;
  summary_counts: {
    completed?: number;
    running?: number;
    failed?: number;
    not_started?: number;
  };
}

export interface NineQuestionRecoveryAction {
  action_id: string;
  label: string;
  kind: string;
  executable: boolean;
  scope?: string | null;
  target?: string | null;
  reason?: string | null;
  path?: string | null;
}

export interface NineQuestionRecoveryPlan {
  question_id?: string;
  retriable: boolean;
  rollback_available: boolean;
  partial_retry_available: boolean;
  partial_replace_available: boolean;
  actions: NineQuestionRecoveryAction[];
}

export interface NineQuestionWorkflowModuleRun {
  module_id: string;
  status: string;
  used_fallback?: boolean;
  source?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface NineQuestionWorkflowDependency {
  dependency_id: string;
  required: boolean;
  status: string;
  message?: string | null;
}

export interface NineQuestionWorkflowPluginRun {
  plugin_id: string;
  feature_code?: string | null;
  status: string;
  expected?: boolean;
  attempted?: boolean;
  duration_ms?: number | null;
  output_summary?: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

/**
 * 九问介绍信息 - 每个问题的目标、期望数据和最终输出
 */
export interface NineQuestionIntro {
  questionId: string;
  title: string;
  goal: string; // 目标是什么
  expectedData: string; // 期望获得什么数据
  finalOutput: string; // 最终输出什么
}

export const NINE_QUESTIONS_INTRODUCTIONS: Record<string, NineQuestionIntro> = {
  q1: {
    questionId: "q1",
    title: "我在那",
    goal: "环境态势感知 + 工作区领域归类，识别当前所处的物理和逻辑环境",
    expectedData: "物理主机状态、工作区结构分析、内容采样摘要、不确定性提示",
    finalOutput: "工作区领域推断结果（主领域、次领域、置信度、推理摘要、不确定性列表、建议第一步）",
  },
  q2: {
    questionId: "q2",
    title: "我有什么",
    goal: "统一资产盘点，全面梳理当前可用的认知工具、执行域、Agent、策略补丁和工作区权限",
    expectedData: "认知工具注册表、执行域目录、已连接 Agent 列表、激活的策略补丁、可访问工作区区域",
    finalOutput: "统一资产清单 + 资源评估（资源状态/缺失关键资产/瓶颈节点/推理摘要）",
  },
  q3: {
    questionId: "q3",
    title: "我是谁",
    goal: "角色推演 + 身份内核装配，基于 Q1 的环境态势、Q2 的资产盘点和底层身份约束推断当前最适合的任务角色",
    expectedData: "Q1 态势结果、Q2 资产盘点结果、身份内核（元动机/禁令/不可绕过约束）、主观风险偏好权重、人工干预回执",
    finalOutput: "角色画像（身份角色/活跃角色/任务角色）+ 使命连续性边界（当前使命/优先职责/连续性边界）",
  },
  q4: {
    questionId: "q4",
    title: "我能做什么",
    goal: "能力边界评估，基于 Q2 的资产清单、Q3 的角色推断和当前权限，评估系统真正具备的行动能力",
    expectedData: "Q2 资产清单、Q3 角色画像、活跃执行域、权限边界、Q1-Q3 的前置态势",
    finalOutput: "能力边界画像（能力上限/可行动空间/可执行策略），严格禁止幻觉声明不存在的能力",
  },
  q5: {
    questionId: "q5",
    title: "我不能干什么",
    goal: "禁止边界判断 + 合规性检查，在 Q4 的能力范围内进一步筛选出禁止、未授权和需升级审批的操作",
    expectedData: "Q4 能力边界、联系策略、租户范围、Agent 信任策略、组织边界规则",
    finalOutput: "禁止边界画像（禁止操作空间及原因/需升级动作/联系和组织边界/允许操作对照白名单）",
  },
  q6: {
    questionId: "q6",
    title: "如果我做了会怎样 / 代价与后果是什么",
    goal: "What-if 代价与后果评估，在行动前推演直接后果、传导后果、严重度、可逆性、缓解要求和停止条件",
    expectedData: "可行动空间、Q5 禁止边界、不可绕过约束、历史失败/策略补丁、风险提示",
    finalOutput: "代价与后果画像（ConsequenceAssessment / CostImpactProfile）",
  },
  q7: {
    questionId: "q7",
    title: "我的红线与约束是什么",
    goal: "红线与约束评估，在 Q8 生成行动目标前识别不可绕过底线",
    expectedData: "身份内核底线、Q5 授权边界、安全拒绝记录、程序记忆约束",
    finalOutput: "RedLineAssessment（当前红线命中/拒绝记录/禁令来源/不可绕过约束/引用来源）",
  },
  q8: {
    questionId: "q8",
    title: "我现在应该做什么",
    goal: "任务优先级与目标生成，汇总 Q1-Q7 的约束与能力，生成当前最优主目标和任务队列",
    expectedData: "Q1-Q7 聚合上下文、绝对红线数量、能力天花板计数、持久化任务状态",
    finalOutput: "目标画像（当前主目标/阶段任务/优先级排序）+ 自主任务队列（下一步任务/阻塞任务/主动行动）",
  },
  q9: {
    questionId: "q9",
    title: "我应该如何行动",
    goal: "行动姿态定调，根据 Q1-Q8 的状态确定行动风格、节奏和确认策略",
    expectedData: "Q1-Q8 认知快照、自我模型（认知负荷/稳定性/自信度漂移/近期弱点）、推理预算余量",
    finalOutput: "行动姿态（评估风格/风险容忍度/行动节奏/确认策略/进化方向）",
  },
};

/**
 * 获取九问介绍信息
 */
export function getNineQuestionIntro(questionId: string): NineQuestionIntro | undefined {
  return NINE_QUESTIONS_INTRODUCTIONS[questionId];
}

export interface LLMTokenUsageView {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface LLMTracePayloadView {
  request_id?: string | null;
  decision_id?: string | null;
  provider_name?: string | null;
  model?: string | null;
  system_prompt?: string | null;
  prompt?: string | null;
  source_module?: string | null;
  invocation_phase?: string | null;
  question_driver_refs?: string[];
  context_data: Record<string, any>;
  raw_response?: Record<string, any> | null;
  token_usage: LLMTokenUsageView;
  elapsed_ms?: number | null;
  error_type?: string | null;
  error_message?: string | null;
  invocations?: LLMTracePayloadView[];
}

export interface Q9LlmTaskRow {
  session_id: string;
  task_scope: "internal" | "external" | string;
  task_index: number;
  task_key: string;
  trace_id?: string | null;
  request_id?: string | null;
  decision_id?: string | null;
  provider_name?: string | null;
  model?: string | null;
  task_name: string;
  task_description: string;
  plan_objective?: string | null;
  elapsed_ms?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Q9LlmTaskDetail extends Q9LlmTaskRow {
  q8_task?: Record<string, any> | string | null;
  llm_input?: Record<string, any> | null;
  llm_output?: Record<string, any> | null;
  token_usage?: LLMTokenUsageView | Record<string, any> | null;
}

export interface Q9LlmTasksPayload {
  question_id: "q9" | string;
  session_id: string;
  source_table: string;
  task_count: number;
  tasks: Q9LlmTaskRow[];
}

export interface Q9LlmTaskDetailPayload {
  question_id: "q9" | string;
  session_id: string;
  source_table: string;
  task: Q9LlmTaskDetail;
}

export interface Q1LLMUpgradeProfileView {
  objective_summary: string;
  target_component: string;
  target_metric: string;
  baseline_version: string;
  recommended_dataset: string;
  validation_commands: string[];
}

export interface Q1LLMUpgradeView {
  planning_status: string;
  profile?: Q1LLMUpgradeProfileView | null;
  candidate_version?: string | null;
  release_gate?: string | null;
  error_message?: string | null;
}


export interface NineQuestionSandboxResponse {
  question_id: string;
  title: string;
  tool_id: string;
  summary: string;
  confidence: number;
  trace_id: string;
  elapsed_ms: number;
  provider_name?: string | null;
  mounted_plugins?: MountedPluginInfo[];
  prompt?: string | null;
  context: Record<string, any>;
  result: any;
  context_updates: Record<string, any>;
  preprocessed_evidence?:
    | Q1PreprocessedEvidence
    | Q2PreprocessedEvidence
    | Q3PreprocessedEvidence
    | Q4PreprocessedEvidence
    | Q5PreprocessedEvidence
    | Q6PreprocessedEvidence
    | Q7PreprocessedEvidence
    | Q8PreprocessedEvidence
    | Q9PreprocessedEvidence
    | null;
  inference_result?:
    | WorkspaceDomainInferenceView
    | Q2WhoAmIInferenceView
    | Q3WhatDoIHaveInferenceView
    | Q4WhatCanIDoInferenceView
    | Q5WhatAmIAllowedToDoInferenceView
    | Q6ConsequenceInferenceView
    | Q7AlternativeStrategyInferenceView
    | Q8WhatShouldIDoNowInferenceView
    | Q9ActionPostureInferenceView
    | null;
  llm_trace_payload?: LLMTracePayloadView | null;
  q1_llm_upgrade?: Q1LLMUpgradeView | null;
}

export interface NineQuestionsRunResponse {
  started: boolean;
  trace_id: string;
  refresh_reason: string;
  snapshot_version: number;
  revision: number;
}

const NINE_QUESTION_FETCH_TIMEOUT_MS = 8000;
const HEAVY_NINE_QUESTION_FETCH_TIMEOUT_MS = 30000;

function getNineQuestionFetchTimeout(questionId: string): number {
  return questionId === "q2" ? HEAVY_NINE_QUESTION_FETCH_TIMEOUT_MS : NINE_QUESTION_FETCH_TIMEOUT_MS;
}

async function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit, timeoutMs = NINE_QUESTION_FETCH_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: init?.signal ?? controller.signal,
    });
  } catch (error) {
    if ((error as Error)?.name === "AbortError") {
      throw new Error(`请求超时（>${timeoutMs}ms）`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export interface Q1WorkspaceSampleSummary {
  path?: string;
  file?: string;
  title?: string;
  header?: string;
  summary?: string;
  snippet?: string;
  excerpt?: string;
  first_lines?: string;
}

export interface Q1StructureTreeRow {
  row_id: string;
  path: string;
  label: string;
  depth: number;
  kind: string;
  file_count?: number | null;
  summary?: string | null;
}

export interface Q1CandidateGroupDetail {
  group_id: string;
  label: string;
  file_count?: number | null;
  summary?: string | null;
}

export interface Q1RiskFileDetail {
  path: string;
  severity?: string | null;
  reason?: string | null;
}

export interface Q1LongTextEvidence {
  evidence_id: string;
  label: string;
  kind: string;
  source: string;
  path?: string | null;
  text: string;
}

export interface Q1PreprocessedEvidence {
  physical_and_environment: {
    environment_event: Record<string, any>;
    physical_host_state: Record<string, any>;
    memory_pressure?: string | null;
    network_health?: string | null;
    memory_pressure_status: string;
    network_health_status: string;
    environment_summary: string[];
  };
  workspace_structure: {
    directory_hierarchy_summary?: string | null;
    top_level_dirs: string[];
    file_total_count?: number | null;
    suffix_distribution: Record<string, number>;
    high_frequency_filename_keywords: Record<string, number>;
    candidate_groups: string[];
    obvious_risk_files: string[];
    directory_tree_rows: Q1StructureTreeRow[];
    candidate_group_details: Q1CandidateGroupDetail[];
    obvious_risk_file_details: Q1RiskFileDetail[];
    analyzer_snapshot: Record<string, any>;
  };
  workspace_content_sampling: {
    sampled_file_summaries: Q1WorkspaceSampleSummary[];
    log_anomaly_snippets: string[];
    long_text_evidence: Q1LongTextEvidence[];
    sample_count: number;
    anomaly_count: number;
    sampler_snapshot: Record<string, any>;
  };
}

export interface WorkspaceDomainInferenceView {
  primary_domain: string;
  secondary_domains: string[];
  confidence: number;
  reasoning_summary: string;
  uncertainties: string[];
  suggested_first_step: string;
  host_runtime_type?: string | null;
  host_runtime_reason?: string | null;
}

export interface Q2Q1Summary {
  primary_domain: string;
  secondary_domains: string[];
  uncertainties: string[];
  risk_summary?: string | null;
}

export interface Q2IdentityKernel {
  meta_motivation: string;
  values_prohibition: string;
  non_bypassable_constraints: string[];
}

export interface Q2ManualIntervention {
  latest_manual_role_modification: string | null;
  applied_at: string | null;
}

export interface Q2PreprocessedEvidence {
  q1_summary?: Q2Q1Summary;
  identity_kernel?: Q2IdentityKernel;
  manual_intervention?: Q2ManualIntervention | null;
  workspace_permission?: Record<string, any>;
  tools_agents?: Record<string, any>;
  memory_strategy?: Record<string, any>;
  asset_inventory?: Q3AssetInventoryView;
}

export interface Q2RoleView {
  identity_role: string;
  active_role: string;
  inferred_reference_role: string;
  role_alignment_gap: string;
  task_role: string;
}

export interface Q2MissionBoundaryView {
  current_mission: string;
  priority_duties: string[];
  continuity_boundaries: string[];
}

export interface Q2RoleAlignmentJudgementView {
  user_configured_role: string;
  inferred_reference_role: string;
  role_alignment_gap: string;
  q2_computed_role_profile: Record<string, any>;
  final_role_profile: Record<string, any>;
  aligned: boolean;
  replacement_allowed: boolean;
  analysis_source: string;
  analysis: string;
}

export interface Q2WhoAmIInferenceView {
  asset_inventory?: Q3AssetInventoryView;
  sufficiency_assessment?: Q3ResourceSufficiencyView | Record<string, any>;
  role_profile?: Q2RoleView;
  mission_boundary?: Q2MissionBoundaryView;
  role_alignment_judgement?: Q2RoleAlignmentJudgementView | null;
}

export interface Q3WorkspaceAndPermission {
  workspaces: string[];
  tenant_permissions: string[];
  execution_tokens: string[];
}

export interface Q3ToolsAndAgents {
  cognitive_tools: string[];
  execution_tools: string[];
  connected_agents: Array<Record<string, any>>;
  cognitive_tool_rows: Q3AssetRow[];
  execution_tool_rows: Q3AssetRow[];
  connected_agent_rows: Q3AgentRow[];
  mcp_servers: Array<{
    server_id: string;
    transport_type: string;
    status: string;
    tool_count: number;
    tools?: Array<{
      tool_name: string;
      description: string;
      plugin_id: string;
      feature_code: string;
    }>;
  }>;
  cli_tools: Array<{
    command_name: string;
    description: string;
    mapped_domain: string;
    plugin_id: string;
    feature_code: string;
    read_only: boolean;
    status: string;
  }>;
}

export interface Q3AssetRow {
  id: string;
  name: string;
  introduction: string;
  function_description: string;
}

export interface Q3AgentRow extends Q3AssetRow {
  status?: string | null;
}

export interface Q3MemoryAndStrategy {
  experience_logs: string[];
  strategy_patches: string[];
}

export interface Q3AssetInventoryItemView {
  asset_name: string;
  description: string;
  source: string;
  plugin_category: string;
  trust_level: string;
  validity: string;
}

export interface Q3AssetInventoryView {
  inventory_summary?: string;
  long_term_memory?: Q3AssetInventoryItemView[];
  cognitive_and_functional_tools?: Q3AssetInventoryItemView[];
  connected_agents?: Q3AssetInventoryItemView[];
  strategy_patches?: Q3AssetInventoryItemView[];
}

export interface Q3PreprocessedEvidence {
  workspace_permission: Q3WorkspaceAndPermission;
  tools_agents: Q3ToolsAndAgents;
  memory_strategy: Q3MemoryAndStrategy;
  asset_inventory?: Q3AssetInventoryView;
  q1_environment_inference?: Record<string, any>;
  q2_asset_inventory?: Q3AssetInventoryView;
  q1_llm_trace_payload?: LLMTracePayloadView | Record<string, any>;
  q2_llm_trace_payload?: LLMTracePayloadView | Record<string, any>;
  identity_kernel_snapshot?: Record<string, any>;
}

export interface Q3ResourceSufficiencyView {
  resource_status: string;
  resource_status_label?: string | null;
  resource_status_explanation?: string | null;
  missing_critical_assets: string[];
  bottleneck_node?: string | null;
  reasoning_summary?: string | null;
}

export interface Q3WhatDoIHaveInferenceView {
  asset_inventory?: Q3AssetInventoryView;
  sufficiency_assessment?: Q3ResourceSufficiencyView;
  role_profile?: Q2RoleView;
  mission_boundary?: Q2MissionBoundaryView;
}

export interface Q4PreprocessedEvidence {
  q1_context: Record<string, any>;
  q2_context: Record<string, any>;
  q3_inventory: Record<string, any>;
}

export interface Q4WhatCanIDoInferenceView {
  capability_upper_limits: string[];
  actionable_space: string[];
  executable_strategies: string[];
}

export interface Q5PreprocessedEvidence {
  actionable_space: string[];
  contact_policy: string[];
  tenant_boundaries: string[];
  agent_trust_status: Record<string, string>;
}

export interface Q5WhatAmIAllowedToDoInferenceView {
  authorization_boundary?: Record<string, any>;
  current_authorization_scope?: string;
  contact_policies?: string[];
  organizational_boundaries?: string;
  allowed_actions?: string[];
  forbidden_actions?: string[];
  question_driver_refs?: string[];
  execution_tier: string;
  interaction_scope: string;
  requires_human_confirmation: boolean;
  requires_cloud_audit: boolean;
  explicitly_forbidden_actions: string[];
  compliance_risks: string[];
  allowed_delegation_targets: string[];
}

export interface Q6PreprocessedEvidence {
  actionable_space: string[];
  authorization_boundaries: string[];
  non_bypassable_constraints: string[];
  historical_strategy_patches: string[];
}

export interface Q6ConsequenceInferenceView {
  ConsequenceAssessment?: {
    action_under_review?: string;
    immediate_consequences?: string[];
    downstream_consequences?: string[];
    consequence_severity?: string;
    reversibility?: string;
  };
  CostImpactProfile?: {
    operational_costs?: string[];
    security_compliance_impacts?: string[];
    user_trust_impacts?: string[];
    mitigation_requirements?: string[];
    stop_conditions?: string[];
  };
  action_under_review?: string;
  immediate_consequences?: string[];
  downstream_consequences?: string[];
  consequence_severity?: string;
  reversibility?: string;
  operational_costs?: string[];
  security_compliance_impacts?: string[];
  user_trust_impacts?: string[];
  mitigation_requirements?: string[];
  stop_conditions?: string[];
}

export interface Q7PreprocessedEvidence {
  identity_kernel_constraints: string[];
  authorization_boundary_constraints: string[];
  safety_rejection_history: string[];
  procedural_memory_constraints: string[];
  non_bypassable_constraints: string[];
  ban_source_explanations: string[];
  question_driver_refs: string[];
}

export interface Q7AlternativeStrategyInferenceView {
  current_red_line_hits: string[];
  rejected_operation_records: string[];
  ban_source_explanations: string[];
  non_bypassable_constraints: string[];
  question_driver_refs: string[];
}

export interface Q8AggregatedContextEvidence {
  q1_to_q7_snapshot: Record<string, any>;
  absolute_red_line_count: number;
  capability_ceiling_count: number;
}

export interface Q8PersistentTaskItem {
  item_id: string;
  title: string;
  status: string;
  priority?: number | null;
  blocker_reason?: string | null;
}

export interface Q8AgendaItem {
  item_id: string;
  title: string;
  status: string;
  priority?: number | null;
  next_review_condition?: string | null;
  delay_risk_score?: number | null;
}

export interface Q8RuntimeStateEvidence {
  persistent_task_state: Q8PersistentTaskItem[];
  cognitive_agenda: Q8AgendaItem[];
}

export interface Q8PreprocessedEvidence {
  aggregated_context: Q8AggregatedContextEvidence;
  runtime_state: Q8RuntimeStateEvidence;
}

export interface Q8ObjectiveProfileView {
  current_primary_objective: string;
  current_phase_tasks: string[];
  priority_order: string[];
}

export interface Q8AutonomousTaskQueueView {
  next_self_tasks: Array<Record<string, any>>;
  blocked_self_tasks: Array<Record<string, any>>;
  proactive_actions: Array<Record<string, any>>;
}

export interface Q8WhatShouldIDoNowInferenceView {
  objective_profile: Q8ObjectiveProfileView;
  task_queue: Q8AutonomousTaskQueueView;
  q8_internal_cognitive_tasks?: Array<Record<string, any>>;
  q8_external_execution_tasks?: Array<Record<string, any>>;
}

export interface Q9CognitiveSnapshotEvidence {
  q1_to_q8_snapshot: Record<string, any>;
  uncertainty_count: number;
  absolute_red_line_count: number;
}

export interface Q9RecentWeaknessView {
  pattern_id?: string | null;
  pattern_type: string;
  frequency?: number | null;
  severity?: string | null;
}

export interface Q9SelfModelEvidence {
  cognitive_load: string;
  stability_level?: string | null;
  confidence_drift?: number | null;
  recent_weaknesses: Q9RecentWeaknessView[];
}

export interface Q9ReasoningBudgetEvidence {
  compute_remaining_ratio: number;
  token_remaining_ratio: number;
  time_remaining_ratio: number;
  budget_pressure?: string | null;
}

export interface Q9PreprocessedEvidence {
  cognitive_snapshot: Q9CognitiveSnapshotEvidence;
  self_model: Q9SelfModelEvidence;
  reasoning_budget: Q9ReasoningBudgetEvidence;
}

export interface Q9ActionPostureInferenceView {
  evaluation_style: string;
  risk_tolerance: string;
  action_rhythm: string;
  confirmation_strategy: string;
  evolution_direction: string;
}

export interface MountedPluginInfo {
  plugin_id: string;
  display_name?: string;
  source_kind: string; // "base", "patch"
  version: string;
  description: string;
  function_description?: string;
  status: string; // "active", "candidate", "degraded", "revoked"
}

export interface NineQuestionItem {
  question_id: string;
  title: string;
  tool_id: string;
  summary: string;
  confidence: number;
  result: any;
  context_updates: Record<string, any>;
  trace_id: string;
  timestamp: string;
  cache_status?: string;
  provider_name?: string | null;
  mounted_plugins?: MountedPluginInfo[];
  preprocessed_evidence?:
    | Q1PreprocessedEvidence
    | Q2PreprocessedEvidence
    | Q3PreprocessedEvidence
    | Q4PreprocessedEvidence
    | Q5PreprocessedEvidence
    | Q6PreprocessedEvidence
    | Q7PreprocessedEvidence
    | Q8PreprocessedEvidence
    | Q9PreprocessedEvidence
    | null;
  inference_result?:
    | WorkspaceDomainInferenceView
    | Q2WhoAmIInferenceView
    | Q3WhatDoIHaveInferenceView
    | Q4WhatCanIDoInferenceView
    | Q5WhatAmIAllowedToDoInferenceView
    | Q6ConsequenceInferenceView
    | Q7AlternativeStrategyInferenceView
    | Q8WhatShouldIDoNowInferenceView
    | Q9ActionPostureInferenceView
    | null;
  llm_trace_payload?: LLMTracePayloadView | null;
  q1_llm_upgrade?: Q1LLMUpgradeView | null;
}
export interface ReportPayload {
  session_id?: string;
  status: string;
  status_message: string | null;
  last_turn_id: string;
  snapshot_version: number;
  revision: number;
  refreshed_at: string | null;
  last_refresh_reason: string | null;
  question_driver_refs: string[];
  questions: NineQuestionItem[];
}

export interface TraceDetail {
  trace_id: string;
  prompt: string | null;
  context: any;
  result: any;
  invocation_phase: string | null;
  source_module: string | null;
  provider_plugin_id?: string | null;
  provider_name?: string | null;
  question_driver_refs?: string[];
  invoked_at?: string;
  completed_at?: string | null;
  failed_at?: string | null;
  related_events?: TraceRelatedEvent[];
  preprocessed_evidence?:
    | Q1PreprocessedEvidence
    | Q2PreprocessedEvidence
    | Q3PreprocessedEvidence
    | Q4PreprocessedEvidence
    | Q5PreprocessedEvidence
    | Q6PreprocessedEvidence
    | Q7PreprocessedEvidence
    | Q8PreprocessedEvidence
    | Q9PreprocessedEvidence
    | null;
  inference_result?:
    | WorkspaceDomainInferenceView
    | Q2WhoAmIInferenceView
    | Q3WhatDoIHaveInferenceView
    | Q4WhatCanIDoInferenceView
    | Q5WhatAmIAllowedToDoInferenceView
    | Q6ConsequenceInferenceView
    | Q7AlternativeStrategyInferenceView
    | Q8WhatShouldIDoNowInferenceView
    | Q9ActionPostureInferenceView
    | null;
  llm_trace_payload?: LLMTracePayloadView | null;
  q1_llm_upgrade?: Q1LLMUpgradeView | null;
}

export async function readResponseBody(resp: Response): Promise<any> {
  if (typeof resp.text === "function") {
    const raw = await resp.text();
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch {
      return { detail: raw };
    }
  }
  if (typeof resp.json === "function") {
    return resp.json();
  }
  return null;
}

function extractApiErrorMessage(data: any, fallback: string): string {
  const detail = data?.detail;
  if (typeof detail?.user_message === "string" && detail.user_message.trim()) {
    return detail.user_message;
  }
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (typeof detail?.error === "string" && detail.error.trim()) {
    return detail.error;
  }
  if (typeof detail?.reason === "string" && detail.reason.trim()) {
    return detail.reason;
  }
  return fallback;
}

export async function fetchNineQuestionsReport(): Promise<{
  report: ReportPayload;
  notice: string | null;
}> {
  const resp = await fetch("/api/web/nine-questions/latest-report");
  const data = await readResponseBody(resp);

  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");

    if (resp.status === 404 && detail === "No active session") {
      return {
        report: {
          status: "ready",
          status_message: null,
          last_turn_id: "0",
          snapshot_version: 0,
          revision: 0,
          refreshed_at: null,
          last_refresh_reason: null,
          question_driver_refs: [],
          questions: [],
        },
        notice: "当前没有活动 session。先跑一次九问流程，再回到这个测试页刷新。",
      };
    }

    throw new Error(detail || `获取九问报告失败（HTTP ${resp.status}）`);
  }

  return {
    report: data,
    notice:
      data?.status === "initializing"
        ? null
        : !Array.isArray(data?.questions) || data.questions.length === 0
        ? "当前 session 里还没有九问结果。运行一次九问后再刷新查看。"
        : null,
  };
}

export async function fetchNineQuestionsStatus(): Promise<{
  report: ReportPayload;
  notice: string | null;
}> {
  const resp = await fetch("/api/web/nine-questions/status");
  const data = await readResponseBody(resp);

  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");

    if (resp.status === 404 && detail === "No active session") {
      return {
        report: {
          session_id: "-",
          status: "ready",
          status_message: null,
          last_turn_id: "0",
          snapshot_version: 0,
          revision: 0,
          refreshed_at: null,
          last_refresh_reason: null,
          question_driver_refs: [],
          questions: [],
        },
        notice: "当前没有活动 session。先跑一次九问流程，再回到这个测试页刷新。",
      };
    }

    throw new Error(detail || `获取九问状态失败（HTTP ${resp.status}）`);
  }

  return {
    report: data,
    notice:
      data?.status === "initializing"
        ? null
        : !Array.isArray(data?.questions) || data.questions.length === 0
        ? "当前 session 里还没有九问结果。运行一次九问后再刷新查看。"
        : null,
  };
}


export async function runAllNineQuestions(forceRefresh = false): Promise<NineQuestionsRunResponse> {
  const resp = await fetch("/api/web/nine-questions/run-all", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ force_refresh: forceRefresh }),
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `执行完整九问流程失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionsRunResponse;
}

export async function runSingleNineQuestion(
  questionId: string,
  forceRefresh = true,
  runPayload?: Record<string, unknown>,
): Promise<NineQuestionsRunResponse> {
  const resp = await fetch(`/api/web/nine-questions/${questionId}/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ force_refresh: forceRefresh, ...(runPayload ?? {}) }),
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `执行 ${questionId} 单独重跑失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionsRunResponse;
}

export async function rollbackSingleNineQuestion(questionId: string): Promise<NineQuestionsRunResponse> {
  const resp = await fetch(`/api/web/nine-questions/${questionId}/rollback`, {
    method: "POST",
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `执行 ${questionId} 回滚失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionsRunResponse;
}

export async function executeNineQuestionRecoveryAction(action: NineQuestionRecoveryAction): Promise<NineQuestionsRunResponse> {
  if (!action.executable) {
    throw new Error(`${action.label || action.action_id} 当前只是计划动作，尚未接入执行器`);
  }
  if (!action.path) {
    throw new Error(`${action.label || action.action_id} 缺少后端路径`);
  }
  const resp = await fetch(action.path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `执行恢复动作失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionsRunResponse;
}

export async function rollbackNineQuestionModule(questionId: string, moduleId: string): Promise<NineQuestionsRunResponse> {
  const resp = await fetch(`/api/web/nine-questions/${questionId}/modules/${moduleId}/rollback`, {
    method: "POST",
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `执行 ${questionId}.${moduleId} 模块回滚失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionsRunResponse;
}

export async function retryNineQuestionModule(questionId: string, moduleId: string): Promise<NineQuestionsRunResponse> {
  const resp = await fetch(`/api/web/nine-questions/${questionId}/modules/${moduleId}/retry`, {
    method: "POST",
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `执行 ${questionId}.${moduleId} 模块重试失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionsRunResponse;
}

export async function fetchNineQuestionTrace(traceId: string): Promise<TraceDetail> {
  // Validate trace ID before making the request
  if (!traceId || traceId === "none" || traceId.endsWith(":no-trace")) {
    throw new Error(`Invalid trace ID: ${traceId}`);
  }
  
  const resp = await fetch(`/api/web/nine-questions/traces/${traceId}`);
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取 trace 失败（HTTP ${resp.status}）`);
  }
  return data;
}

export async function runNineQuestionSandboxTest(
  qId: string,
  mockContext: Record<string, any>,
): Promise<NineQuestionSandboxResponse> {
  const resp = await fetch(`/api/web/nine-questions/${qId}/test`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ mock_context: mockContext }),
  });
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `执行九问沙箱测试失败（HTTP ${resp.status}）`);
  }
  return data;
}

export async function fetchNineQuestionDetail(
  questionId: string,
  traceId?: string,
): Promise<NineQuestionItem> {
  const url = traceId
    ? `/api/web/nine-questions/${questionId}?trace_id=${encodeURIComponent(traceId)}`
    : `/api/web/nine-questions/${questionId}`;

  const resp = await fetchWithTimeout(url, undefined, getNineQuestionFetchTimeout(questionId));
  const data = await readResponseBody(resp);

  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");

    if (resp.status === 404 && detail === "No active session") {
      throw new Error("当前没有活动 session。请先运行一次九问推演流程，再刷新此页。");
    }
    if (resp.status === 404) {
      throw new Error(
        detail ||
          `${questionId.toUpperCase()} 尚无快照记录。请先运行一次完整的九问推演流程，再回到此页查看。`,
      );
    }
    if (resp.status === 503) {
      throw new Error(
        detail ||
          "九问状态机未挂载到运行时。请检查 Zentex Brain Runtime 是否正常启动。",
      );
    }
    throw new Error(detail || `获取 ${questionId} 详情失败（HTTP ${resp.status}）。`);
  }

  return data as NineQuestionItem;
}

async function _fetchQuestionSubSection(questionId: string, section: string): Promise<Record<string, any>> {
  const resp = await fetchWithTimeout(
    `/api/web/nine-questions/${questionId}/${section}`,
    undefined,
    getNineQuestionFetchTimeout(questionId),
  );
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取 ${questionId} ${section} 失败（HTTP ${resp.status}）`);
  }
  return (data as Record<string, any>) ?? {};
}

export async function fetchNineQuestionSummary(questionId: string): Promise<Record<string, any>> {
  return _fetchQuestionSubSection(questionId, "summary");
}

export async function fetchNineQuestionEvidence(questionId: string): Promise<Record<string, any>> {
  return _fetchQuestionSubSection(questionId, "evidence");
}

export async function fetchNineQuestionInference(questionId: string): Promise<Record<string, any>> {
  return _fetchQuestionSubSection(questionId, "inference");
}

export async function fetchNineQuestionTracePayload(questionId: string): Promise<Record<string, any>> {
  return _fetchQuestionSubSection(questionId, "trace-payload");
}

export async function fetchQ9LlmTasks(): Promise<Q9LlmTasksPayload> {
  const resp = await fetchWithTimeout(
    "/api/web/nine-questions/q9/llm-tasks",
    undefined,
    getNineQuestionFetchTimeout("q9"),
  );
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取 q9 llm tasks 失败（HTTP ${resp.status}）`);
  }
  return data as Q9LlmTasksPayload;
}

export async function fetchQ9LlmTaskDetail(taskKey: string): Promise<Q9LlmTaskDetailPayload> {
  const resp = await fetchWithTimeout(
    `/api/web/nine-questions/q9/llm-tasks/${encodeURIComponent(taskKey)}`,
    undefined,
    getNineQuestionFetchTimeout("q9"),
  );
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取 q9 llm task ${taskKey} 失败（HTTP ${resp.status}）`);
  }
  return data as Q9LlmTaskDetailPayload;
}

export async function fetchQ2LlmTrace(): Promise<Record<string, any>> {
  const resp = await fetchWithTimeout(
    "/api/web/nine-questions/q2/llm",
    undefined,
    getNineQuestionFetchTimeout("q2"),
  );
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取 q2 llm 失败（HTTP ${resp.status}）`);
  }
  return (data as Record<string, any>) ?? {};
}

export async function fetchNineQuestionRaw(questionId: string): Promise<Record<string, any>> {
  return _fetchQuestionSubSection(questionId, "raw");
}

export async function fetchQ2AssetStatistics(): Promise<Record<string, any>> {
  const resp = await fetchWithTimeout(
    "/api/web/nine-questions/q2/asset-statistics",
    undefined,
    getNineQuestionFetchTimeout("q2"),
  );
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取 q2 asset-statistics 失败（HTTP ${resp.status}）`);
  }
  return (data as Record<string, any>) ?? {};
}

export async function fetchNineQuestionModules(questionId: string): Promise<Record<string, any>> {
  return _fetchQuestionSubSection(questionId, "modules");
}

export async function fetchNineQuestionReflections(
  questionId?: string,
): Promise<NineQuestionReflectionRecord[]> {
  const url = questionId
    ? `/api/web/reflections?q_id=${encodeURIComponent(questionId)}`
    : `/api/web/reflections`;
  const resp = await fetch(url);
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取反思记录失败（HTTP ${resp.status}）`);
  }
  return (data?.items ?? []) as NineQuestionReflectionRecord[];
}

export async function fetchNineQuestionReflectionDetail(
  reflectionId: string,
): Promise<NineQuestionReflectionRecord> {
  const resp = await fetch(`/api/web/reflections/${encodeURIComponent(reflectionId)}`);
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取反思详情失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionReflectionRecord;
}

export async function fetchNineQuestionWorkflow(): Promise<NineQuestionWorkflowPayload> {
  const resp = await fetch("/api/web/nine-questions/workflow");
  const data = await readResponseBody(resp);
  if (!resp.ok) {
    const detail = extractApiErrorMessage(data, "");
    throw new Error(detail || `获取九问工作流状态失败（HTTP ${resp.status}）`);
  }
  return data as NineQuestionWorkflowPayload;
}

export function getQuestionDisplayLabel(questionId: string): string {
  const labels: Record<string, string> = {
    q1: "Q1_Where_Am_I",
    q2: "Q2_What_Do_I_Have",
    q3: "Q3_Who_Am_I",
    q4: "Q4_What_Can_I_Do",
    q5: "Q5_What_Can_I_Not_Do",
    q6: "Q6_What_If_I_Do_It",
    q7: "Q7_What_Else_Can_I_Do",
    q8: "Q8_What_Should_I_Do_Now",
    q9: "Q9_How_Should_I_Act",
  };
  return labels[questionId] || questionId.toUpperCase();
}
