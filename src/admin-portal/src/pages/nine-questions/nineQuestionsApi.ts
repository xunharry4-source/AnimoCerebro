
export interface TraceRelatedEvent {
  entry_id: string;
  entry_type: string;
  timestamp: string;
  trace_id: string;
  payload: any;
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
    | Q6ForbiddenZoneInferenceView
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
  q1_summary: Q2Q1Summary;
  identity_kernel: Q2IdentityKernel;
  manual_intervention?: Q2ManualIntervention | null;
}

export interface Q2RoleView {
  identity_role: string;
  active_role: string;
  task_role: string;
}

export interface Q2MissionBoundaryView {
  current_mission: string;
  priority_duties: string[];
  continuity_boundaries: string[];
}

export interface Q2WhoAmIInferenceView {
  role_profile: Q2RoleView;
  mission_boundary: Q2MissionBoundaryView;
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

export interface Q3PreprocessedEvidence {
  workspace_permission: Q3WorkspaceAndPermission;
  tools_agents: Q3ToolsAndAgents;
  memory_strategy: Q3MemoryAndStrategy;
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
  sufficiency_assessment: Q3ResourceSufficiencyView;
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

export interface Q6ForbiddenZoneInferenceView {
  absolute_red_lines: string[];
  performance_tradeoff_bans: string[];
  prohibited_strategies: string[];
  contamination_risks: string[];
}

export interface Q7PreprocessedEvidence {
  resource_bottlenecks: string[];
  capability_limits: string[];
  permission_boundaries: string[];
  absolute_red_lines: string[];
  historical_failure_patches: string[];
}

export interface Q7AlternativeStrategyInferenceView {
  fallback_plans: string[];
  degradation_strategies: string[];
  collaboration_switches: Array<Record<string, any>>;
  exploratory_actions: string[];
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
    | Q6ForbiddenZoneInferenceView
    | Q7AlternativeStrategyInferenceView
    | Q8WhatShouldIDoNowInferenceView
    | Q9ActionPostureInferenceView
    | null;
  llm_trace_payload?: LLMTracePayloadView | null;
  q1_llm_upgrade?: Q1LLMUpgradeView | null;
}
export interface ReportPayload {
  session_id: string;
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
    | Q6ForbiddenZoneInferenceView
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

export async function runAllNineQuestions(forceRefresh = true): Promise<NineQuestionsRunResponse> {
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

export async function fetchNineQuestionTrace(traceId: string): Promise<TraceDetail> {
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

  const resp = await fetch(url);
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

export function getQuestionDisplayLabel(questionId: string): string {
  const labels: Record<string, string> = {
    q1: "Q1_Where_Am_I",
    q2: "Q2_Who_Am_I",
    q3: "Q3_What_Do_I_Have",
    q4: "Q4_What_Can_I_Do",
    q5: "Q5_What_Am_I_Allowed_To_Do",
    q6: "Q6_What_Should_I_Not_Do",
    q7: "Q7_What_Else_Can_I_Do",
    q8: "Q8_What_Should_I_Do_Now",
    q9: "Q9_How_Should_I_Act",
  };
  return labels[questionId] || questionId.toUpperCase();
}
