# nine-question-q5-what-am-i-allowed-to-do

- Name: Q5 What Can I Not Do
- Description: Generate Q5 safety rules, filter Q4 objective candidates, and bind passed candidates to applicable safety-rule refs.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Product Semantics

Q5 answers: 我不能干什么 / 哪些安全规则适用于本轮目标。

Q5 is the system safety-rule publisher and Q4 objective filter. It is not a generic authorization page and does not generate objectives, evaluate consequences, write plans, explore more possibilities, create tasks, or execute anything.

Q5 produces three auditable V1.5 product artifacts:

- `GlobalSafetyRuleSet`
- `Q4ObjectiveSafetyFilterResult`
- `CandidateSafetyRuleBinding[]`

Q5 filters Q4 objective candidates before they reach Q6, Q8, Q9, or G31A:

- Q4 objective seeds and objective candidates must enter Q5 before Q6/Q8/Q9.
- Q7 executable discoveries must first return to Q4 for objective expression, then enter Q5 as ordinary Q4 candidates.
- Q5 may block, pass, or require rewrite for Q4 candidates.
- Q5 may bind passed candidates to applicable safety-rule refs and required guardrail tags.
- `hard_blocked` objectives must not enter Q6/Q8/Q9/G31A.
- `conditional_allowed` objectives may enter Q6 only so Q6 can generate restrictions, consequences, risk controls, and avoidance conditions.
- `hard_blocked` cannot be overridden by Q6, Q7, Q8, Q9, `force_execute`, value ranking, or priority.
- Q5 rule bindings are declarative refs. They are not Q6 costs, Q7 alternatives, Q8 task choices, Q9 steps, rollback plans, or execution instructions.

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public service boundary.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.
- Functional plugin outputs may provide source evidence for safety-rule synthesis, Q4 candidate filtering, and candidate-rule binding. They must not widen allowed objective scope beyond Q4/Q5.

## Input Semantics

Q5 may consume upstream facts, stable governance material, and Q4 candidates:

- Q1 LLM analysis, including current environment, workspace boundary, visible risks, and environment objective signals.
- Q2 LLM analysis, including self-observation, internal function status, external tool profile refs, validation state, permissions, side effects, and task routing hints.
- Q3 `effective_role`, human-role priority decisions, and role-delta reports.
- Q4 `ObjectiveSeedSet`, `ObjectiveCandidateSet`, `ObjectiveSignalRefs`, and `CapabilityBoundaryEvidenceRefs`.
- Q7-returned executable candidates only after they have been re-expressed by Q4.
- Human-configured roles, forbidden actions, authorization boundaries, and non-overridable commitments.
- IdentityKernel, SafetyGate, supervision, audit-chain, memory-integrity, and subject-continuity constraints.
- Protected module lists, internal function profiles, historical incidents, Reflection/Experience risk evidence, platform or organization policy refs, G12/G30 policy summaries, and connector/tool profile refs.
- Tenant scope, contact policy, agent trust policy, permission boundaries, forbidden actions, and workspace policy evidence.

Q5 must not use Q6/Q7/Q8/Q9 downstream results to define, soften, or rewrite its safety rules. Q7 output is valid Q5 input only after it has returned through Q4 and become a new `ObjectiveCandidate`.

## Configured Forbidden Actions

The settings page allows the user to configure workspace-level forbidden actions. These settings are persisted on the workspace as `forbidden_actions`.

Q5 must treat configured forbidden actions as first-class review input:

- `query_nine_question_forbidden_items(...)` must read `workspace.forbidden_actions` from the current/default workspace when building Q5 review evidence.
- Configured forbidden actions must be included in Q5's forbidden-item evidence together with IdentityKernel constraints and SafetyGate redlines.
- During internal and external Q5 review, any Q4 objective candidate that matches or attempts to bypass a configured forbidden action must be blocked or gated according to the Q5 boundary contract.
- The configured forbidden action source must remain auditable through the Q5 evidence refs or source metadata.

## Internal Lane Documentation

The Q5 internal plugin is `q5_internal_safety_rule_binding`: 内部总安全规则、目标过滤与规则绑定.

Its responsibility is to generate internal `GlobalSafetyRuleSet`, filter Q4 internal objective candidates, and bind passed candidates to applicable safety rules. It is the internal lane version of the V1.5 Q5 contract, not an authorization helper and not a Q6/Q7/Q8/Q9 planner.

Internal inputs:

- `Q1LLM分析结果`
- `Q2LLM分析结果`
- `Q3身份假设结果`, using only `effective_role` as the effective identity boundary
- `Q4内部目标候选集`
- `人类设置禁令列表`
- `IdentityKernel安全边界`
- `内部不可自改写模块清单`
- `内部功能画像与学习说明`
- `历史安全事故与反思摘要`
- `系统级安全策略摘要`
- `trace_id`

Internal output root:

- `Q5InternalSafetyRuleBindingPackage`

Internal output must include:

- `question_id="Q5"`, `question_text="我不能干什么"`, `lane="internal"`, `trace_id`, `package_id`, and `package_version`
- `generated_from` refs for Q1/Q2/Q3/Q4, human config, IdentityKernel, internal function profiles, historical risks, and policies
- `global_safety_rule_set.rules`
- `q4_objective_filter_result.blocked_candidates`
- `q4_objective_filter_result.passed_candidates`
- `q4_objective_filter_result.requires_rewrite_candidates`
- `candidate_safety_rule_bindings`
- `handoff.consumer_modules=["Q6", "Q7", "Q8", "Q9", "G31A"]`
- `unsupported_or_missing_inputs`
- `blocked_or_invalid`

Internal Q5 rule bindings may use guardrail tags such as `no_identity_kernel_write`, `no_safety_module_write`, `read_only_only`, and `requires_human_authorization`. These tags are only declarative rule refs. They must not become execution steps, backup plans, rollback plans, Plan B, substitute objectives, cost analysis, or task design.

Internal Q5 must block or require rewrite when a candidate attempts to overwrite, delete, bypass, or weaken `identity`, `safety`, `supervision`, `audit`, `cloud_audit`, the task-center state machine, memory integrity, subject continuity, human-set role boundaries, or other protected modules. It must not upgrade an internal cognition plugin into a physical side-effect executor.

## Public Methods

Q5 exposes two lane-specific public methods. Callers must choose the lane they need and must not ask downstream code to split, normalize, or clean a mixed Q5 payload.

### `run_internal_tool(context)`

Use this method for internal cognition and memory/identity/safety-module boundaries only.

Returns a `CognitiveToolResult` with:

- `tool_id`: `<q5_plugin_id>:internal`
- `llm_output`:
  - `q5_internal_llm_input`
  - `q5_internal_llm_output`
- `context_updates`:
  - `q5_internal_cannot_do_boundary`
  - `q5_internal_authorization_boundary`
  - `q5_internal_execution_diagnosis`
- `proposals`:
  - one `q5_internal_cannot_do_boundary` proposal

The V1.5 internal product contract is `Q5InternalSafetyRuleBindingPackage`. Existing `q5_internal_cannot_do_boundary` / `InternalGoalComplianceAssessment` fields are compatibility projections and must stay derived from the safety-rule package, not replace it. When present, the compatibility projection contains:

- `scope`: `internal`
- `boundary_type`: `InternalGoalComplianceAssessment`
- `type`: `InternalGoalComplianceAssessment`
- `system_safety_boundary`
- `blocked_internal_objectives`
- `non_bypassable_internal_constraints`
- `identity_kernel_protection_hits`
- `safety_module_protection_hits`
- `supervision_module_protection_hits`
- `memory_integrity_risks`
- `continuity_risks`
- `allowed_internal_objectives_with_conditions`

If the LLM returns a legacy `AuthorizationBoundary`, an empty object, unknown keys, downstream-step advice, Q6 consequence fields, Q7 exploration fields, Q8 task choices, Q9 plan fields, or otherwise meaningless content, Q5 raises an error. Downstream must not be responsible for interpreting that garbage.

### `run_external_tool(context)`

Use this method for external execution, connector, CLI, MCP, browser, API, tenant, contact, and side-effect boundaries only.

Returns a `CognitiveToolResult` with:

- `tool_id`: `<q5_plugin_id>:external`
- `llm_output`:
  - `q5_external_llm_input`
  - `q5_external_llm_output`
- `context_updates`:
  - `q5_external_cannot_do_boundary`
  - `q5_external_authorization_boundary`
  - `q5_external_execution_diagnosis`
- `proposals`:
  - one `q5_external_cannot_do_boundary` proposal

The meaningful business contract is `q5_external_cannot_do_boundary`. It is already normalized by Q5 and contains an `ExternalGoalComplianceAssessment` with this shape:

- `scope`: `external`
- `boundary_type`: `ExternalGoalComplianceAssessment`
- `type`: `ExternalGoalComplianceAssessment`
- `system_safety_boundary`
- `blocked_external_objectives`
- `requires_cloud_audit`
- `requires_human_confirmation`
- `permission_boundary_hits`
- `data_exfiltration_risks`
- `unauthorized_mutation_risks`
- `allowed_external_objectives_with_conditions`

If the LLM returns a legacy `AuthorizationBoundary`, an empty object, unknown keys, or otherwise meaningless content, Q5 raises an error. Downstream must not be responsible for interpreting that garbage.

### `run_tool(context)`

`run_tool(context)` exists only as a compatibility orchestrator for callers that still execute the Q5 plugin as one cognitive plugin. It calls `run_internal_tool(context)` and `run_external_tool(context)` separately, then returns both lane results side by side.

`run_tool(context)` must not merge internal and external semantics into one authorization object. Its `context_updates` may contain both lane outputs, but the meaningful boundaries remain:

- `q5_internal_cannot_do_boundary`
- `q5_external_cannot_do_boundary`

Downstream code must consume those lane-specific fields directly. It must not parse raw `q5_*_llm_input`, raw `q5_*_llm_output`, or legacy merged fields as the business result.

## Write Locations

- Functional plugin outputs must first be merged into Q5's goal-compliance evidence inputs.
- Preferred input-side merge targets are:
  - `model_context["q4_objective_candidate_set"]`
  - `model_context["q7_returned_objective_candidates"]`
  - `model_context["identity_kernel_constraints"]`
  - `model_context["safety_gate_policy"]`
  - `model_context["supervision_policy"]`
  - `model_context["audit_chain_policy"]`
  - `model_context["memory_integrity_policy"]`
  - `model_context["continuity_constraints"]`
  - `model_context["contact_policy"]`
  - `model_context["tenant_scope"]`
  - `model_context["agent_trust_policy"]`
  - `model_context["forbidden_actions"]`
- `model_context` passed to the LLM must contain only lane-specific Q5 data plus minimal metadata. It must not contain full `nine_question_state`, complete `question_snapshots`, prior Q5 `llm_input`, or prior Q5 `llm_output`.
- The canonical V1.5 product result is the Q5 safety-rule package:
  - `q5_safety_boundary_package`
  - `q5_global_safety_rule_set`
  - `q5_q4_objective_filter_result`
  - `q5_candidate_safety_rule_bindings`
- Existing lane-specific cannot-do boundaries are compatibility projections:
  - `q5_internal_cannot_do_boundary`
  - `q5_external_cannot_do_boundary`
- Q5 must persist or project the canonical result into:
  - `q5_safety_boundary_package`
  - `q5_global_safety_rule_set`
  - `q5_q4_objective_filter_result`
  - `q5_candidate_safety_rule_bindings`
  - `q5_internal_cannot_do_boundary`
  - `q5_external_cannot_do_boundary`
  - `q5_internal_authorization_boundary`
  - `q5_external_authorization_boundary`
  - `q5_objective_convergence_guard`

Legacy merged authorization fields are not canonical Q5 output. Q5 must not expose a single combined `authorization_boundary`, `q5_authorization_boundary`, `q5_authorization_boundary_profile`, or `q5_permission_boundary` as the business result.

## Output Semantics

The internal cognition lane returns `Q5InternalSafetyRuleBindingPackage` with:

- `generated_from`
- `global_safety_rule_set`
- `q4_objective_filter_result`
- `candidate_safety_rule_bindings`
- `handoff`
- `unsupported_or_missing_inputs`
- `blocked_or_invalid`

The compatibility internal projection may expose `InternalGoalComplianceAssessment` with:

- `system_safety_boundary`
- `blocked_internal_objectives`
- `non_bypassable_internal_constraints`
- `identity_kernel_protection_hits`
- `safety_module_protection_hits`
- `supervision_module_protection_hits`
- `memory_integrity_risks`
- `continuity_risks`
- `allowed_internal_objectives_with_conditions`

The internal lane must first derive the cognitive safety boundary from human settings, `IdentityKernel_NonBypassableConstraints`, `MemoryIntegrity_And_ContinuityRules`, `ProtectedModules_State`, internal function profiles, historical risk evidence, and system policy refs, then filter every `Q4_InternalObjectiveCandidates` item against that boundary. Passed internal objectives must carry applicable rule refs and guardrail tags. Unreferenced unconditional internal release is invalid.

The external execution lane returns `ExternalGoalComplianceAssessment` with:

- `system_safety_boundary`
- `blocked_external_objectives`
- `requires_cloud_audit`
- `requires_human_confirmation`
- `permission_boundary_hits`
- `data_exfiltration_risks`
- `unauthorized_mutation_risks`
- `allowed_external_objectives_with_conditions`

The external lane must first derive the system safety boundary from `SafetyGate_Redlines_External`, `Execution_Rights_Matrix`, and `CloudAudit_Policies`, then filter every `Q4_ExternalObjectiveCandidates` item against that boundary. Allowed external objectives must always include a concrete `compliance_condition`; unconditional external release is invalid.

Each lane result must be meaningful before leaving Q5. Both lanes preserve the safety-boundary statement, blocked objectives, approval/control conditions, and risk-classification fields. Raw LLM output is persisted for audit only; it is not the downstream business contract.

## Constraints

- Deterministic prohibitions must be hard-blocked by code.
- Target disguise, implicit intent, boundary-edge cases, and complex platform/compliance meaning require live LLM semantic assistance and SafetyGate review.
- Q5 live LLM output must be strict JSON and must validate as Q5 safety-rule, Q4 filter, and candidate-rule-binding output.
- Internal objectives must be blocked when they try to overwrite safety modules, the identity kernel, supervision modules, the audit chain, non-self-modifiable modules, unrecoverable memory, or subject-continuity hard constraints.
- External objectives must be blocked or gated when they involve unauthorized deletion, overwrite, data exfiltration, credential misuse, boundary bypass, out-of-scope access, unapproved remote writes, high-risk side-effect tools, execution-gate bypass, or platform abuse.
- Q8 must remove Q5 `hard_blocked` objectives before creating final objectives.
- Q6/Q7/Q8/Q9/G31A consume Q5 rule refs; they must not redefine or weaken Q5's source safety rules.
- The prompt assembly must persist `system_prompt`, injected evidence context, raw response, token usage, and `question_driver_refs` in `llm_trace_payload`.
- Q5 must read upstream Q3/Q4 and policy inputs from the persisted nine-question SQLite per-question tables through the authoritative LLM output projection. It must not read legacy response blobs, MongoDB snapshots, or non-SQLite compatibility data.
- Q5 must persist successful question output, LLM output, trace data, context updates, module runs, and module outputs through the split SQLite nine-question tables. These tables must keep schema version and timestamps.
- Q5 must not use fallback, degradation, compatibility, synthesized policy, or snapshot-only replacement data when Q4 objectives, tenant scope, contact policy, agent trust policy, functional authorization execution, LLM invocation, LLM output validation, or SafetyGate validation fails.
- On exception, Q5 must raise the error and must not save a Q5 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q5 as a fallback/degraded answer and must not fabricate a new LLM output.

## Data Acquisition Enforcement

为了确保因果审计链（Causal Audit Chain）的完整性，Q5 **必须** 遵循以下数据获取规范：

1. **禁止手动提取 (No Manual Extraction)**:
   - 严禁使用 `context.get("q4_...")` 等方式获取 Q4 结果。
   - 严禁从 `nine_question_state` 的 `context_updates` 中直接读取上游数据。

2. **官方加载器路径 (Official Loader Methods)**:
   - 必须通过上游 Q4 提供的对外读取方法从 SQLite 权威状态库中读取数据。
   - 内部轨 (Internal Lane) 数据获取：`from plugins.nine_questions.q4_what_can_i_do.service import load_internal_public_output`
   - 外部轨 (External Lane) 数据获取：`from plugins.nine_questions.q4_what_can_i_do.service import load_external_public_output`

3. **因果处理**:
   - 加载器会自动处理数据清洗、空值过滤及结构化校验，确保进入 LLM Prompt 的上下文是经过因果验证的最新快照。
