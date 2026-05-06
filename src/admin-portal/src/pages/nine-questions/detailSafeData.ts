import {
  Q1PreprocessedEvidence,
  Q2PreprocessedEvidence,
  WorkspaceDomainInferenceView,
  Q2WhoAmIInferenceView,
  Q3PreprocessedEvidence,
  Q3WhatDoIHaveInferenceView,
  Q4PreprocessedEvidence,
  Q4WhatCanIDoInferenceView,
  Q5PreprocessedEvidence,
  Q5WhatAmIAllowedToDoInferenceView,
  Q6ConsequenceInferenceView,
  Q6PreprocessedEvidence,
  Q7AlternativeStrategyInferenceView,
  Q7PreprocessedEvidence,
  Q8PreprocessedEvidence,
  Q8WhatShouldIDoNowInferenceView,
  Q9ActionPostureInferenceView,
  Q9PreprocessedEvidence,
} from "./nineQuestionsApi";

type RecordLike = Record<string, any>;

export interface SanitizedDetailData<T> {
  value: T;
  warnings: string[];
}

function isRecord(value: unknown): value is RecordLike {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown): RecordLike {
  return isRecord(value) ? value : {};
}

function asArray(value: unknown): any[] {
  return Array.isArray(value) ? value : [];
}

function asStringArray(value: unknown): string[] {
  return asArray(value).map((item) => String(item));
}

function parseMaybeJson(value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed || !["{", "["].includes(trimmed[0])) {
    return value;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function asBusinessText(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    const parsed = parseMaybeJson(value);
    if (parsed !== value) {
      return asBusinessText(parsed);
    }
    return value.trim();
  }
  if (Array.isArray(value)) {
    return value.map(asBusinessText).filter(Boolean).join(" / ");
  }
  if (isRecord(value)) {
    const preferred = [
      "summary",
      "description",
      "motivation",
      "value",
      "rule",
      "constraint",
      "reason",
      "intent",
      "name",
      "title",
    ];
    const preferredValues = preferred
      .filter((key) => Object.prototype.hasOwnProperty.call(value, key))
      .map((key) => asBusinessText(value[key]))
      .filter(Boolean);
    const entries = Object.entries(value)
      .filter(([key]) => !preferred.includes(key))
      .map(([key, entryValue]) => {
        const formatted = asBusinessText(entryValue);
        return formatted ? `${key}: ${formatted}` : "";
      })
      .filter(Boolean);
    return [...preferredValues, ...entries].join("；");
  }
  return String(value);
}

function asBusinessTextArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(asBusinessText).filter(Boolean);
  }
  const formatted = asBusinessText(value);
  return formatted ? [formatted] : [];
}

function asTaskQueueItems(value: unknown): Array<RecordLike> {
  if (Array.isArray(value)) {
    const stringItems = value.filter((item) => typeof item === "string") as string[];
    const hasOnlyStrings = stringItems.length === value.length;
    if (hasOnlyStrings) {
      const nonEmptyStrings = stringItems.map((item) => item.trim()).filter(Boolean);
      const looksLikeCharacterSplit =
        nonEmptyStrings.length > 1 && nonEmptyStrings.every((item) => item.length === 1);
      if (looksLikeCharacterSplit) {
        return [{ title: nonEmptyStrings.join("") }];
      }
    }
    return value.map((item) => {
      if (isRecord(item)) {
        return item;
      }
      if (typeof item === "string") {
        return { title: item };
      }
      return { title: String(item) };
    });
  }

  if (typeof value === "string") {
    return value.trim() ? [{ title: value }] : [];
  }

  if (isRecord(value)) {
    return [value];
  }

  if (value === null || value === undefined) {
    return [];
  }

  return [{ title: String(value) }];
}

function pushTypeWarning(warnings: string[], label: string, value: unknown, expected: string) {
  if (value === null || value === undefined) {
    return;
  }
  const actual = Array.isArray(value) ? "array" : typeof value;
  if (expected === "object" && isRecord(value)) {
    return;
  }
  if (expected === "array" && Array.isArray(value)) {
    return;
  }
  warnings.push(`${label} 字段类型异常，期望 ${expected}，实际为 ${actual}。`);
}

export function sanitizeQ1Evidence(rawEvidence: unknown): SanitizedDetailData<Q1PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  const physical = asRecord(evidence.physical_and_environment);
  const workspace = asRecord(evidence.workspace_structure);
  const sampling = asRecord(evidence.workspace_content_sampling);

  pushTypeWarning(warnings, "physical_and_environment", evidence.physical_and_environment, "object");
  pushTypeWarning(warnings, "workspace_structure", evidence.workspace_structure, "object");
  pushTypeWarning(warnings, "workspace_content_sampling", evidence.workspace_content_sampling, "object");
  pushTypeWarning(warnings, "environment_event", physical.environment_event, "object");
  pushTypeWarning(warnings, "physical_host_state", physical.physical_host_state, "object");
  pushTypeWarning(warnings, "environment_summary", physical.environment_summary, "array");
  pushTypeWarning(warnings, "top_level_dirs", workspace.top_level_dirs, "array");
  pushTypeWarning(warnings, "suffix_distribution", workspace.suffix_distribution, "object");
  pushTypeWarning(warnings, "high_frequency_filename_keywords", workspace.high_frequency_filename_keywords, "object");
  pushTypeWarning(warnings, "candidate_groups", workspace.candidate_groups, "array");
  pushTypeWarning(warnings, "obvious_risk_files", workspace.obvious_risk_files, "array");
  pushTypeWarning(warnings, "directory_tree_rows", workspace.directory_tree_rows, "array");
  pushTypeWarning(warnings, "candidate_group_details", workspace.candidate_group_details, "array");
  pushTypeWarning(warnings, "obvious_risk_file_details", workspace.obvious_risk_file_details, "array");
  pushTypeWarning(warnings, "analyzer_snapshot", workspace.analyzer_snapshot, "object");
  pushTypeWarning(warnings, "sampled_file_summaries", sampling.sampled_file_summaries, "array");
  pushTypeWarning(warnings, "log_anomaly_snippets", sampling.log_anomaly_snippets, "array");
  pushTypeWarning(warnings, "long_text_evidence", sampling.long_text_evidence, "array");
  pushTypeWarning(warnings, "sampler_snapshot", sampling.sampler_snapshot, "object");

  return {
    value: {
      physical_and_environment: {
        environment_event: asRecord(physical.environment_event),
        physical_host_state: asRecord(physical.physical_host_state),
        memory_pressure: physical.memory_pressure == null ? null : String(physical.memory_pressure),
        network_health: physical.network_health == null ? null : String(physical.network_health),
        memory_pressure_status: String(physical.memory_pressure_status || "unknown"),
        network_health_status: String(physical.network_health_status || "unknown"),
        environment_summary: asStringArray(physical.environment_summary),
      },
      workspace_structure: {
        directory_hierarchy_summary:
          workspace.directory_hierarchy_summary == null ? null : String(workspace.directory_hierarchy_summary),
        top_level_dirs: asStringArray(workspace.top_level_dirs),
        file_total_count:
          typeof workspace.file_total_count === "number" ? workspace.file_total_count : null,
        suffix_distribution: asRecord(workspace.suffix_distribution) as Record<string, number>,
        high_frequency_filename_keywords:
          asRecord(workspace.high_frequency_filename_keywords) as Record<string, number>,
        candidate_groups: asStringArray(workspace.candidate_groups),
        obvious_risk_files: asStringArray(workspace.obvious_risk_files),
        directory_tree_rows: asArray(workspace.directory_tree_rows) as any,
        candidate_group_details: asArray(workspace.candidate_group_details) as any,
        obvious_risk_file_details: asArray(workspace.obvious_risk_file_details) as any,
        analyzer_snapshot: asRecord(workspace.analyzer_snapshot),
      },
      workspace_content_sampling: {
        sampled_file_summaries: asArray(sampling.sampled_file_summaries) as any,
        log_anomaly_snippets: asStringArray(sampling.log_anomaly_snippets),
        long_text_evidence: asArray(sampling.long_text_evidence) as any,
        sample_count: typeof sampling.sample_count === "number" ? sampling.sample_count : 0,
        anomaly_count: typeof sampling.anomaly_count === "number" ? sampling.anomaly_count : 0,
        sampler_snapshot: asRecord(sampling.sampler_snapshot),
      },
    },
    warnings,
  };
}

export function sanitizeQ1Inference(
  rawInference: unknown,
): SanitizedDetailData<WorkspaceDomainInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  pushTypeWarning(warnings, "secondary_domains", inference.secondary_domains, "array");
  pushTypeWarning(warnings, "uncertainties", inference.uncertainties, "array");

  return {
    value: {
      primary_domain: String(inference.primary_domain || ""),
      secondary_domains: asStringArray(inference.secondary_domains),
      confidence: typeof inference.confidence === "number" ? inference.confidence : 0,
      reasoning_summary: String(inference.reasoning_summary || ""),
      uncertainties: asStringArray(inference.uncertainties),
      suggested_first_step: String(inference.suggested_first_step || ""),
      host_runtime_type: inference.host_runtime_type == null ? null : String(inference.host_runtime_type),
      host_runtime_reason: inference.host_runtime_reason == null ? null : String(inference.host_runtime_reason),
    },
    warnings,
  };
}

export function sanitizeQ2Evidence(rawEvidence: unknown): SanitizedDetailData<Q2PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  const workspacePermission = asRecord(evidence.workspace_permission);
  const toolsAgents = asRecord(evidence.tools_agents);
  const memoryStrategy = asRecord(evidence.memory_strategy);
  const assetInventory = asRecord(evidence.asset_inventory);

  pushTypeWarning(warnings, "workspace_permission", evidence.workspace_permission, "object");
  pushTypeWarning(warnings, "tools_agents", evidence.tools_agents, "object");
  pushTypeWarning(warnings, "memory_strategy", evidence.memory_strategy, "object");
  pushTypeWarning(warnings, "asset_inventory", evidence.asset_inventory, "object");

  return {
    value: {
      workspace_permission: workspacePermission,
      tools_agents: toolsAgents,
      memory_strategy: memoryStrategy,
      asset_inventory: assetInventory,
    },
    warnings,
  };
}

export function sanitizeQ2Inference(
  rawInference: unknown,
): SanitizedDetailData<Q2WhoAmIInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  const assetInventory = asRecord(inference.asset_inventory);
  const sufficiency = asRecord(inference.sufficiency_assessment);
  pushTypeWarning(warnings, "inference_result.asset_inventory", inference.asset_inventory, "object");
  pushTypeWarning(warnings, "inference_result.sufficiency_assessment", inference.sufficiency_assessment, "object");
  pushTypeWarning(warnings, "inference_result.sufficiency_assessment.missing_critical_assets", sufficiency.missing_critical_assets, "array");

  return {
    value: {
      asset_inventory: assetInventory,
      sufficiency_assessment: {
        ...sufficiency,
        resource_status: String(sufficiency.resource_status || "unknown"),
        missing_critical_assets: asStringArray(sufficiency.missing_critical_assets),
        bottleneck_node: sufficiency.bottleneck_node == null ? null : String(sufficiency.bottleneck_node),
        reasoning_summary: sufficiency.reasoning_summary == null ? null : String(sufficiency.reasoning_summary),
        resource_status_label:
          sufficiency.resource_status_label == null ? null : String(sufficiency.resource_status_label),
        resource_status_explanation:
          sufficiency.resource_status_explanation == null
            ? null
            : String(sufficiency.resource_status_explanation),
      },
    },
    warnings,
  };
}

export function sanitizeQ3Evidence(rawEvidence: unknown): SanitizedDetailData<Q3PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  const workspacePermission = asRecord(evidence.workspace_permission);
  const toolsAgents = asRecord(evidence.tools_agents);
  const memoryStrategy = asRecord(evidence.memory_strategy);
  const assetInventory = asRecord(evidence.asset_inventory);
  const q1Environment = asRecord(evidence.q1_environment_inference);
  const q2AssetInventory = asRecord(evidence.q2_asset_inventory);
  const q1LlmTrace = asRecord(evidence.q1_llm_trace_payload);
  const q2LlmTrace = asRecord(evidence.q2_llm_trace_payload);
  const identityKernel = asRecord(evidence.identity_kernel_snapshot);

  pushTypeWarning(warnings, "workspace_permission", evidence.workspace_permission, "object");
  pushTypeWarning(warnings, "tools_agents", evidence.tools_agents, "object");
  pushTypeWarning(warnings, "memory_strategy", evidence.memory_strategy, "object");
  pushTypeWarning(warnings, "workspace_permission.workspaces", workspacePermission.workspaces, "array");
  pushTypeWarning(warnings, "workspace_permission.tenant_permissions", workspacePermission.tenant_permissions, "array");
  pushTypeWarning(warnings, "workspace_permission.execution_tokens", workspacePermission.execution_tokens, "array");
  pushTypeWarning(warnings, "tools_agents.connected_agents", toolsAgents.connected_agents, "array");
  pushTypeWarning(warnings, "tools_agents.cognitive_tool_rows", toolsAgents.cognitive_tool_rows, "array");
  pushTypeWarning(warnings, "tools_agents.execution_tool_rows", toolsAgents.execution_tool_rows, "array");
  pushTypeWarning(warnings, "tools_agents.connected_agent_rows", toolsAgents.connected_agent_rows, "array");
  pushTypeWarning(warnings, "tools_agents.mcp_servers", toolsAgents.mcp_servers, "array");
  pushTypeWarning(warnings, "tools_agents.cli_tools", toolsAgents.cli_tools, "array");
  pushTypeWarning(warnings, "memory_strategy.experience_logs", memoryStrategy.experience_logs, "array");
  pushTypeWarning(warnings, "memory_strategy.strategy_patches", memoryStrategy.strategy_patches, "array");
  pushTypeWarning(warnings, "asset_inventory", evidence.asset_inventory, "object");

  return {
    value: {
      workspace_permission: {
        ...workspacePermission,
        workspaces: asStringArray(workspacePermission.workspaces),
        tenant_permissions: asStringArray(workspacePermission.tenant_permissions),
        execution_tokens: asStringArray(workspacePermission.execution_tokens),
      },
      tools_agents: {
        ...toolsAgents,
        cognitive_tools: asStringArray(toolsAgents.cognitive_tools),
        execution_tools: asStringArray(toolsAgents.execution_tools),
        connected_agents: asArray(toolsAgents.connected_agents),
        cognitive_tool_rows: asArray(toolsAgents.cognitive_tool_rows),
        execution_tool_rows: asArray(toolsAgents.execution_tool_rows),
        connected_agent_rows: asArray(toolsAgents.connected_agent_rows),
        mcp_servers: asArray(toolsAgents.mcp_servers),
        cli_tools: asArray(toolsAgents.cli_tools),
      },
      memory_strategy: {
        ...memoryStrategy,
        experience_logs: asStringArray(memoryStrategy.experience_logs),
        strategy_patches: asStringArray(memoryStrategy.strategy_patches),
      },
      asset_inventory: assetInventory,
      q1_environment_inference: q1Environment,
      q2_asset_inventory: q2AssetInventory,
      q1_llm_trace_payload: q1LlmTrace,
      q2_llm_trace_payload: q2LlmTrace,
      identity_kernel_snapshot: identityKernel,
    },
    warnings,
  };
}

export function sanitizeQ3Inference(rawInference: unknown): SanitizedDetailData<Q3WhatDoIHaveInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  const roleProfile = asRecord(inference.role_profile);
  const missionBoundary = asRecord(inference.mission_boundary);
  pushTypeWarning(warnings, "role_profile", inference.role_profile, "object");
  pushTypeWarning(warnings, "mission_boundary", inference.mission_boundary, "object");
  pushTypeWarning(warnings, "mission_boundary.priority_duties", missionBoundary.priority_duties, "array");
  pushTypeWarning(
    warnings,
    "mission_boundary.continuity_boundaries",
    missionBoundary.continuity_boundaries,
    "array",
  );

  return {
    value: {
      role_profile: {
        identity_role: String(roleProfile.identity_role || ""),
        active_role: String(roleProfile.active_role || ""),
        inferred_reference_role: String(roleProfile.inferred_reference_role || ""),
        role_alignment_gap: String(roleProfile.role_alignment_gap || ""),
        task_role: String(roleProfile.task_role || ""),
      },
      mission_boundary: {
        current_mission: String(missionBoundary.current_mission || ""),
        priority_duties: asStringArray(missionBoundary.priority_duties),
        continuity_boundaries: asStringArray(missionBoundary.continuity_boundaries),
      },
    },
    warnings,
  };
}

export function sanitizeQ4Evidence(rawEvidence: unknown): SanitizedDetailData<Q4PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  pushTypeWarning(warnings, "q1_context", evidence.q1_context, "object");
  pushTypeWarning(warnings, "q2_context", evidence.q2_context, "object");
  pushTypeWarning(warnings, "q3_inventory", evidence.q3_inventory, "object");

  return {
    value: {
      q1_context: asRecord(evidence.q1_context),
      q2_context: asRecord(evidence.q2_context),
      q3_inventory: asRecord(evidence.q3_inventory),
    },
    warnings,
  };
}

export function sanitizeQ4Inference(rawInference: unknown): SanitizedDetailData<Q4WhatCanIDoInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  pushTypeWarning(warnings, "capability_upper_limits", inference.capability_upper_limits, "array");
  pushTypeWarning(warnings, "actionable_space", inference.actionable_space, "array");
  pushTypeWarning(warnings, "executable_strategies", inference.executable_strategies, "array");

  return {
    value: {
      capability_upper_limits: asStringArray(inference.capability_upper_limits),
      actionable_space: asStringArray(inference.actionable_space),
      executable_strategies: asStringArray(inference.executable_strategies),
    },
    warnings,
  };
}

export function sanitizeQ5Evidence(rawEvidence: unknown): SanitizedDetailData<Q5PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  pushTypeWarning(warnings, "actionable_space", evidence.actionable_space, "array");
  pushTypeWarning(warnings, "contact_policy", evidence.contact_policy, "array");
  pushTypeWarning(warnings, "tenant_boundaries", evidence.tenant_boundaries, "array");
  pushTypeWarning(warnings, "agent_trust_status", evidence.agent_trust_status, "object");

  return {
    value: {
      actionable_space: asStringArray(evidence.actionable_space),
      contact_policy: asStringArray(evidence.contact_policy),
      tenant_boundaries: asStringArray(evidence.tenant_boundaries),
      agent_trust_status: asRecord(evidence.agent_trust_status) as Record<string, string>,
    },
    warnings,
  };
}

export function sanitizeQ5Inference(rawInference: unknown): SanitizedDetailData<Q5WhatAmIAllowedToDoInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  const authorizationBoundary = asRecord(inference.authorization_boundary);
  pushTypeWarning(warnings, "authorization_boundary", inference.authorization_boundary, "object");
  pushTypeWarning(warnings, "contact_policies", inference.contact_policies, "array");
  pushTypeWarning(warnings, "allowed_actions", inference.allowed_actions, "array");
  pushTypeWarning(warnings, "forbidden_actions", inference.forbidden_actions, "array");
  pushTypeWarning(warnings, "question_driver_refs", inference.question_driver_refs, "array");
  pushTypeWarning(warnings, "explicitly_forbidden_actions", inference.explicitly_forbidden_actions, "array");
  pushTypeWarning(warnings, "compliance_risks", inference.compliance_risks, "array");
  pushTypeWarning(warnings, "allowed_delegation_targets", inference.allowed_delegation_targets, "array");

  return {
    value: {
      authorization_boundary: authorizationBoundary,
      current_authorization_scope: String(inference.current_authorization_scope || ""),
      contact_policies: asStringArray(inference.contact_policies),
      organizational_boundaries: String(inference.organizational_boundaries || ""),
      allowed_actions: asStringArray(inference.allowed_actions),
      forbidden_actions: asStringArray(inference.forbidden_actions),
      question_driver_refs: asStringArray(inference.question_driver_refs),
      execution_tier: String(inference.execution_tier || ""),
      interaction_scope: String(inference.interaction_scope || ""),
      requires_human_confirmation: Boolean(inference.requires_human_confirmation),
      requires_cloud_audit: Boolean(inference.requires_cloud_audit),
      explicitly_forbidden_actions: asStringArray(inference.explicitly_forbidden_actions),
      compliance_risks: asStringArray(inference.compliance_risks),
      allowed_delegation_targets: asStringArray(inference.allowed_delegation_targets),
    },
    warnings,
  };
}

export function sanitizeQ6Evidence(rawEvidence: unknown): SanitizedDetailData<Q6PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  pushTypeWarning(warnings, "actionable_space", evidence.actionable_space, "array");
  pushTypeWarning(warnings, "authorization_boundaries", evidence.authorization_boundaries, "array");
  pushTypeWarning(warnings, "non_bypassable_constraints", evidence.non_bypassable_constraints, "array");
  pushTypeWarning(warnings, "historical_strategy_patches", evidence.historical_strategy_patches, "array");

  return {
    value: {
      actionable_space: asStringArray(evidence.actionable_space),
      authorization_boundaries: asStringArray(evidence.authorization_boundaries),
      non_bypassable_constraints: asStringArray(evidence.non_bypassable_constraints),
      historical_strategy_patches: asStringArray(evidence.historical_strategy_patches),
    },
    warnings,
  };
}

export function sanitizeQ6Inference(rawInference: unknown): SanitizedDetailData<Q6ConsequenceInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  const consequence = asRecord(inference.ConsequenceAssessment || inference.consequence_assessment);
  const cost = asRecord(inference.CostImpactProfile || inference.cost_impact_profile);
  pushTypeWarning(warnings, "ConsequenceAssessment", inference.ConsequenceAssessment || inference.consequence_assessment, "object");
  pushTypeWarning(warnings, "CostImpactProfile", inference.CostImpactProfile || inference.cost_impact_profile, "object");
  pushTypeWarning(warnings, "immediate_consequences", consequence.immediate_consequences, "array");
  pushTypeWarning(warnings, "downstream_consequences", consequence.downstream_consequences, "array");
  pushTypeWarning(warnings, "operational_costs", cost.operational_costs, "array");
  pushTypeWarning(warnings, "security_compliance_impacts", cost.security_compliance_impacts, "array");
  pushTypeWarning(warnings, "user_trust_impacts", cost.user_trust_impacts, "array");
  pushTypeWarning(warnings, "mitigation_requirements", cost.mitigation_requirements, "array");
  pushTypeWarning(warnings, "stop_conditions", cost.stop_conditions, "array");

  return {
    value: {
      ConsequenceAssessment: {
        action_under_review: String(consequence.action_under_review || ""),
        immediate_consequences: asStringArray(consequence.immediate_consequences),
        downstream_consequences: asStringArray(consequence.downstream_consequences),
        consequence_severity: String(consequence.consequence_severity || ""),
        reversibility: String(consequence.reversibility || ""),
      },
      CostImpactProfile: {
        operational_costs: asStringArray(cost.operational_costs),
        security_compliance_impacts: asStringArray(cost.security_compliance_impacts),
        user_trust_impacts: asStringArray(cost.user_trust_impacts),
        mitigation_requirements: asStringArray(cost.mitigation_requirements),
        stop_conditions: asStringArray(cost.stop_conditions),
      },
    },
    warnings,
  };
}

export function sanitizeQ7Evidence(rawEvidence: unknown): SanitizedDetailData<Q7PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  pushTypeWarning(warnings, "identity_kernel_constraints", evidence.identity_kernel_constraints, "array");
  pushTypeWarning(warnings, "authorization_boundary_constraints", evidence.authorization_boundary_constraints, "array");
  pushTypeWarning(warnings, "safety_rejection_history", evidence.safety_rejection_history, "array");
  pushTypeWarning(warnings, "procedural_memory_constraints", evidence.procedural_memory_constraints, "array");
  pushTypeWarning(warnings, "non_bypassable_constraints", evidence.non_bypassable_constraints, "array");
  pushTypeWarning(warnings, "ban_source_explanations", evidence.ban_source_explanations, "array");
  pushTypeWarning(warnings, "question_driver_refs", evidence.question_driver_refs, "array");

  return {
    value: {
      identity_kernel_constraints: asStringArray(evidence.identity_kernel_constraints),
      authorization_boundary_constraints: asStringArray(evidence.authorization_boundary_constraints),
      safety_rejection_history: asStringArray(evidence.safety_rejection_history),
      procedural_memory_constraints: asStringArray(evidence.procedural_memory_constraints),
      non_bypassable_constraints: asStringArray(evidence.non_bypassable_constraints),
      ban_source_explanations: asStringArray(evidence.ban_source_explanations),
      question_driver_refs: asStringArray(evidence.question_driver_refs),
    },
    warnings,
  };
}

export function sanitizeQ7Inference(rawInference: unknown): SanitizedDetailData<Q7AlternativeStrategyInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  pushTypeWarning(warnings, "inference_result.current_red_line_hits", inference.current_red_line_hits, "array");
  pushTypeWarning(warnings, "inference_result.rejected_operation_records", inference.rejected_operation_records, "array");
  pushTypeWarning(warnings, "inference_result.ban_source_explanations", inference.ban_source_explanations, "array");
  pushTypeWarning(warnings, "inference_result.non_bypassable_constraints", inference.non_bypassable_constraints, "array");
  pushTypeWarning(warnings, "inference_result.question_driver_refs", inference.question_driver_refs, "array");

  return {
    value: {
      current_red_line_hits: asStringArray(inference.current_red_line_hits),
      rejected_operation_records: asStringArray(inference.rejected_operation_records),
      ban_source_explanations: asStringArray(inference.ban_source_explanations),
      non_bypassable_constraints: asStringArray(inference.non_bypassable_constraints),
      question_driver_refs: asStringArray(inference.question_driver_refs),
    },
    warnings,
  };
}

export function sanitizeQ8Evidence(rawEvidence: unknown): SanitizedDetailData<Q8PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  const aggregatedContext = asRecord(evidence.aggregated_context);
  const runtimeState = asRecord(evidence.runtime_state);

  pushTypeWarning(warnings, "aggregated_context", evidence.aggregated_context, "object");
  pushTypeWarning(warnings, "runtime_state", evidence.runtime_state, "object");
  pushTypeWarning(warnings, "aggregated_context.q1_to_q7_snapshot", aggregatedContext.q1_to_q7_snapshot, "object");
  pushTypeWarning(warnings, "runtime_state.persistent_task_state", runtimeState.persistent_task_state, "array");
  pushTypeWarning(warnings, "runtime_state.cognitive_agenda", runtimeState.cognitive_agenda, "array");

  return {
    value: {
      aggregated_context: {
        ...aggregatedContext,
        q1_to_q7_snapshot: asRecord(aggregatedContext.q1_to_q7_snapshot),
        absolute_red_line_count: Number(aggregatedContext.absolute_red_line_count || 0),
        capability_ceiling_count: Number(aggregatedContext.capability_ceiling_count || 0),
      },
      runtime_state: {
        ...runtimeState,
        persistent_task_state: asArray(runtimeState.persistent_task_state),
        cognitive_agenda: asArray(runtimeState.cognitive_agenda),
      },
    },
    warnings,
  };
}

export function sanitizeQ8Inference(rawInference: unknown): SanitizedDetailData<Q8WhatShouldIDoNowInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);
  const objectiveProfile = asRecord(inference.objective_profile);
  const taskQueue = asRecord(inference.task_queue);
  const hasObjectiveData =
    Object.keys(objectiveProfile).length > 0 ||
    typeof inference.current_primary_objective === "string" ||
    Array.isArray(inference.current_phase_tasks) ||
    Array.isArray(inference.priority_order);
  const hasTaskQueueData =
    Object.keys(taskQueue).length > 0 ||
    Array.isArray(inference.next_self_tasks) ||
    Array.isArray(inference.blocked_self_tasks) ||
    Array.isArray(inference.proactive_actions) ||
    Array.isArray(inference.q8_internal_cognitive_tasks) ||
    Array.isArray(inference.q8_external_execution_tasks);

  if (!hasObjectiveData && !hasTaskQueueData) {
    return { value: null, warnings };
  }

  pushTypeWarning(warnings, "inference_result.objective_profile", inference.objective_profile, "object");
  pushTypeWarning(warnings, "inference_result.task_queue", inference.task_queue, "object");
  pushTypeWarning(warnings, "objective_profile.current_phase_tasks", objectiveProfile.current_phase_tasks, "array");
  pushTypeWarning(warnings, "objective_profile.priority_order", objectiveProfile.priority_order, "array");
  if (!(Array.isArray(taskQueue.next_self_tasks) || typeof taskQueue.next_self_tasks === "string" || taskQueue.next_self_tasks == null)) {
    pushTypeWarning(warnings, "task_queue.next_self_tasks", taskQueue.next_self_tasks, "array");
  }
  if (!(Array.isArray(taskQueue.blocked_self_tasks) || typeof taskQueue.blocked_self_tasks === "string" || taskQueue.blocked_self_tasks == null)) {
    pushTypeWarning(warnings, "task_queue.blocked_self_tasks", taskQueue.blocked_self_tasks, "array");
  }
  if (!(Array.isArray(taskQueue.proactive_actions) || typeof taskQueue.proactive_actions === "string" || taskQueue.proactive_actions == null)) {
    pushTypeWarning(warnings, "task_queue.proactive_actions", taskQueue.proactive_actions, "array");
  }

  return {
    value: {
      objective_profile: {
        ...objectiveProfile,
        current_primary_objective: String(objectiveProfile.current_primary_objective || ""),
        current_phase_tasks: asStringArray(objectiveProfile.current_phase_tasks),
        priority_order: asStringArray(objectiveProfile.priority_order),
      },
      task_queue: {
        ...taskQueue,
        next_self_tasks: asTaskQueueItems(taskQueue.next_self_tasks),
        blocked_self_tasks: asTaskQueueItems(taskQueue.blocked_self_tasks),
        proactive_actions: asTaskQueueItems(taskQueue.proactive_actions),
      },
      q8_internal_cognitive_tasks: asTaskQueueItems(inference.q8_internal_cognitive_tasks),
      q8_external_execution_tasks: asTaskQueueItems(inference.q8_external_execution_tasks),
    },
    warnings,
  };
}

export function sanitizeQ9Evidence(rawEvidence: unknown): SanitizedDetailData<Q9PreprocessedEvidence> {
  const warnings: string[] = [];

  if (!isRecord(rawEvidence)) {
    pushTypeWarning(warnings, "preprocessed_evidence", rawEvidence, "object");
  }

  const evidence = asRecord(rawEvidence);
  const cognitiveSnapshot = asRecord(evidence.cognitive_snapshot);
  const selfModel = asRecord(evidence.self_model);
  const reasoningBudget = asRecord(evidence.reasoning_budget);

  pushTypeWarning(warnings, "cognitive_snapshot", evidence.cognitive_snapshot, "object");
  pushTypeWarning(warnings, "self_model", evidence.self_model, "object");
  pushTypeWarning(warnings, "reasoning_budget", evidence.reasoning_budget, "object");
  pushTypeWarning(warnings, "cognitive_snapshot.q1_to_q8_snapshot", cognitiveSnapshot.q1_to_q8_snapshot, "object");
  pushTypeWarning(warnings, "self_model.recent_weaknesses", selfModel.recent_weaknesses, "array");

  return {
    value: {
      cognitive_snapshot: {
        ...cognitiveSnapshot,
        q1_to_q8_snapshot: asRecord(cognitiveSnapshot.q1_to_q8_snapshot),
        uncertainty_count: Number(cognitiveSnapshot.uncertainty_count || 0),
        absolute_red_line_count: Number(cognitiveSnapshot.absolute_red_line_count || 0),
      },
      self_model: {
        ...selfModel,
        cognitive_load: String(selfModel.cognitive_load || "unknown"),
        stability_level: selfModel.stability_level == null ? null : String(selfModel.stability_level),
        confidence_drift:
          typeof selfModel.confidence_drift === "number" ? selfModel.confidence_drift : null,
        recent_weaknesses: asArray(selfModel.recent_weaknesses),
      },
      reasoning_budget: {
        ...reasoningBudget,
        compute_remaining_ratio: Number(reasoningBudget.compute_remaining_ratio || 0),
        token_remaining_ratio: Number(reasoningBudget.token_remaining_ratio || 0),
        time_remaining_ratio: Number(reasoningBudget.time_remaining_ratio || 0),
        budget_pressure: reasoningBudget.budget_pressure == null ? null : String(reasoningBudget.budget_pressure),
      },
    },
    warnings,
  };
}

export function sanitizeQ9Inference(rawInference: unknown): SanitizedDetailData<Q9ActionPostureInferenceView | null> {
  const warnings: string[] = [];

  if (rawInference === null || rawInference === undefined) {
    return { value: null, warnings };
  }

  if (!isRecord(rawInference)) {
    pushTypeWarning(warnings, "inference_result", rawInference, "object");
    return { value: null, warnings };
  }

  const inference = asRecord(rawInference);

  return {
    value: {
      evaluation_style: String(inference.evaluation_style || ""),
      risk_tolerance: String(inference.risk_tolerance || ""),
      action_rhythm: String(inference.action_rhythm || ""),
      confirmation_strategy: String(inference.confirmation_strategy || ""),
      evolution_direction: String(inference.evolution_direction || ""),
    },
    warnings,
  };
}
