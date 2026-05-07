# nine-question-q6-what-should-i-not-do

- Name: Q6 What If I Do It
- Description: Add plan constraints, consequence limits, rationality checks, evidence requirements, rollback requirements, pause conditions, and stop conditions for Q5-approved objectives.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Product Semantics

Q6 answers: 给计划加限制 / 代价、后果、合理性与注意事项。

Q6 runs after Q5 and before Q8. It constrains objectives that passed Q5 so later task design does not ignore consequences, rationality, evidence, rollback, pause, or stop conditions.

Q6 does not decide whether an objective is allowed. Q5 owns that. Q6 does not decide what should be done. Q4/Q8 own that. Q6 does not write plans, split steps, create tasks, or execute anything.

Q6 outputs are mandatory constraints for Q8/Q9:

- Q5 `hard_blocked` objectives must not enter Q6.
- Q5 `conditional_allowed` objectives enter Q6 with their conditions.
- Q6 must turn allowed and conditional objectives into `PlanConstraintSet` entries.
- Q8 must convert Q6 constraints into task-design constraints.
- Q9 must treat Q6 constraints as implementation-plan guardrails.

## Internal Lane Documentation

The Q6 internal plugin is the internal `PlanConstraintSet` and `ConsequenceAndRationalityAssessment` producer for Q5-passed internal objectives.

Its responsibility is to constrain internal goals before Q8/Q9 design any task or implementation plan. It answers what the cost, impact, unreasonable setup, evidence requirement, pause condition, stop condition, rollback requirement, and must-avoid pattern would be if the internal objective proceeds.

Internal inputs:

- `Q4目标种子`
- `Q5安全规则包`
- `Q5_AllowedInternalObjectives`
- `Q5 candidate_safety_rule_bindings` for the objective
- `LivingSelfModel_Snapshot`
- `内部资源预算`
- `历史失败与反思`
- `证据要求摘要`
- `回滚能力摘要`

Internal output root:

- `InternalPlanConstraintSet`

Internal output must include `constraints_by_objective`, and every entry must include:

- `objective_reference`
- `cognitive_cost`
- `memory_impact`
- `reflection_overuse_risk`
- `learning_overfit_risk`
- `value_drift_risk`
- `strategy_pollution_risk`
- `self_evolution_failure_modes`
- `sandbox_requirements`
- `verification_requirements`
- `pause_conditions`
- `stop_conditions`
- `rollback_requirements`
- `must_avoid`

Internal Q6 must not decide whether an objective is allowed. It must not revive Q5 `hard_blocked` candidates, change Q5 rule refs, create alternative Q7 possibilities, select Q8 tasks, draft Q9 steps, generate task IDs, or execute anything. `pause_conditions`, `stop_conditions`, `rollback_requirements`, and `must_avoid` are mandatory safety fields, not optional notes.

## Public Methods

The plugin exposes separate public methods for the internal and external lanes. They are not aliases for one combined output and must not be merged by Q6.

### `run_internal_consequence_profile(context)`

Runs only the internal Q6 lane and returns only the validated internal business profile:

```json
{
  "type": "InternalPlanConstraintSet",
  "constraints_by_objective": [
    {
      "objective_reference": "string",
      "cognitive_cost": "string",
      "memory_impact": "string",
      "reflection_overuse_risk": "string",
      "learning_overfit_risk": "string",
      "value_drift_risk": "string",
      "strategy_pollution_risk": "string",
      "self_evolution_failure_modes": "string",
      "sandbox_requirements": "string",
      "verification_requirements": "string",
      "pause_conditions": "string",
      "stop_conditions": "string",
      "rollback_requirements": "string",
      "must_avoid": ["string"]
    }
  ]
}
```

The internal lane only consumes Q5-approved internal objectives and the living self-model snapshot:

- `Q5_AllowedInternalObjectives`
- `LivingSelfModel_Snapshot`

It must not decide whether those objectives are allowed, and it must not write implementation steps.

This method does not return LLM debug wrappers, raw `llm_input`, raw `llm_output`, or external-lane fields. LLM request/response audit data is persisted separately through the internal module output rows:

- `q6_internal_llm_request`
- `q6_internal_consequence_llm`

### `run_external_consequence_profile(context)`

Runs only the external Q6 lane and returns only the validated external business profile:

```json
{
  "type": "ExternalPlanConstraintSet",
  "objective_constraints": [
    {
      "objective_ref": "string",
      "consequence_and_cost": {
        "physical_side_effects": "string",
        "blast_radius": "string",
        "data_exposure_risk": "string",
        "file_or_remote_mutation_risk": "string",
        "monetary_cost": "string",
        "compute_cost": "string",
        "latency_cost": "string",
        "rollback_difficulty": "string"
      },
      "execution_safeguards": {
        "read_only_probe_first": true,
        "sandbox_first": false,
        "dry_run_first": true,
        "backup_required": true,
        "confirmation_required": false
      },
      "verification_contracts": {
        "evidence_requirements": "string",
        "receipt_requirements": "string"
      },
      "halt_conditions": {
        "pause_conditions": "string",
        "stop_conditions": "string"
      },
      "rationality_assessment": "string"
    }
  ]
}
```

The external lane only consumes Q5-approved external objectives, host state, and execution rights:

- `Q5_AllowedExternalObjectives_WithConditions`
- `Physical_Host_State_External`
- `Execution_Rights_Matrix`

It must not decide whether those objectives are allowed, and it must not write implementation steps.

This method does not return LLM debug wrappers, raw `llm_input`, raw `llm_output`, or internal-lane fields. LLM request/response audit data is persisted separately through the external module output rows:

- `q6_external_llm_request`
- `q6_external_consequence_llm`

### `run_tool(context)`

`run_tool(context)` is an orchestrator only. It calls the internal and external methods separately, records module runs, and publishes two distinct context update keys:

- `q6_internal_consequence_profile`
- `q6_external_consequence_profile`

It must not create a combined `q6_consequence_profile`, merged `llm_output`, or any other internal/external mixed payload. Downstream modules must receive meaningful Q6 lane outputs from these two explicit fields, not parse raw LLM output or infer validity from debugging data.

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public service boundary.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.
- Functional plugin outputs are consequence evidence, scene-specific safety hints, cost evidence, rollback evidence, and verification evidence. They must not approve or revive Q5 `hard_blocked` objectives.

## Input Semantics

Q6 may consume:

- Q4 objective candidates as source objective references.
- Q5 `GoalComplianceAssessment`, `SystemSafetyBoundary`, internal/external compliance assessments, and conditional-allowed refs.
- Global constraints, redline hints, failure history, risk history, resource budget, and execution-environment constraints.
- Compatibility projections such as `q5_authorization_boundary_profile` and `q5_permission_boundary` only as evidence/read-model inputs.

Q6 must not use Q7/Q8/Q9 downstream results to rewrite cost, consequence, rationality, or plan constraints.

## Write Locations

- Functional plugin outputs must first be merged into Q6's plan-constraint evidence inputs.
- Preferred input-side merge targets are:
  - `model_context["q4_objective_candidate_set"]`
  - `model_context["q5_goal_compliance_assessment"]`
  - `model_context["q5_internal_goal_compliance"]`
  - `model_context["q5_external_goal_compliance"]`
  - `model_context["q5_system_safety_boundary"]`
  - `model_context["q5_conditional_allowed_objective_refs"]`
  - `model_context["global_constraints"]`
  - `model_context["redline_hints"]`
  - `model_context["failure_history"]`
  - `model_context["risk_history"]`
  - `model_context["resource_budget"]`
  - `model_context["execution_environment_constraints"]`
- The canonical product result is `PlanConstraintSet` plus `ConsequenceAndRationalityAssessment`.
- Q6 must persist or project the canonical result into:
  - `q6_plan_constraints`
  - `q6_internal_plan_constraints`
  - `q6_external_plan_constraints`
  - `q6_consequence_and_rationality_assessment`
  - `q6_rationality_verdicts`
  - `q6_preconditions_to_check`
  - `q6_evidence_requirements`
  - `q6_guardrails_during_plan`
  - `q6_rollback_or_abort_strategy`
  - `q6_pause_conditions`
  - `q6_stop_conditions`
  - `q6_simpler_alternatives`
- Legacy read models may still be persisted for compatibility and display:
  - `q6_consequence_assessment`
  - `q6_cost_impact_profile`
  - `q6_consequence_inference`
  - `q6_global_constraints`
  - `q6_redline_hints`
  - `q6_forbidden_zone_profile`

Legacy consequence and forbidden-zone fields are compatibility projections. They must not replace the Q6 product semantic of plan constraints and rationality limits.

## Output Semantics

Q6 has two lane-specific output contracts. The public method return values and context updates must use these contracts.

`InternalPlanConstraintSet` includes `constraints_by_objective`, and each objective constraint includes:

- `objective_reference`
- `cognitive_cost`
- `memory_impact`
- `reflection_overuse_risk`
- `learning_overfit_risk`
- `value_drift_risk`
- `strategy_pollution_risk`
- `self_evolution_failure_modes`
- `sandbox_requirements`
- `verification_requirements`
- `pause_conditions`
- `stop_conditions`
- `rollback_requirements`
- `must_avoid`

`ExternalPlanConstraintSet` includes `objective_constraints`, and each objective constraint includes:

- `objective_ref`
- `consequence_and_cost`
- `execution_safeguards`
- `verification_contracts`
- `halt_conditions`
- `rationality_assessment`

`InternalPlanConstraintSet` and `ExternalPlanConstraintSet` are the lane-specific public return shapes for this plugin. Q6 must reject empty or generic safeguards. Internal `pause_conditions`, `stop_conditions`, `rollback_requirements`, and `must_avoid` are mandatory safety fields. External `halt_conditions`, physical evidence requirements, receipt requirements, and high-risk safeguard consistency are mandatory safety fields.

The external execution lane must still reason about:

- `physical_side_effects`
- `blast_radius`
- `data_exposure_risk`
- `file_or_remote_mutation_risk`
- `monetary_cost`
- `compute_cost`
- `latency_cost`
- `rollback_difficulty`
- `evidence_requirements`
- `receipt_requirements`
- `read_only_probe_first`
- `sandbox_first`
- `dry_run_first`
- `backup_required`
- `confirmation_required`
- `pause_conditions`
- `stop_conditions`

## Constraints

- Q6 LLM output must be strict JSON and must validate into the lane-specific public profile before Q6 returns anything to downstream consumers.
- Q6 must use live LLM reasoning for cost, impact, irrational plans, bad consequences, simpler alternatives, and edge-case tradeoffs.
- Hard constraints remain enforced by code and SafetyGate.
- Internal constraints must cover over-reflection, memory corruption, ungrounded strategy patches, value drift, identity-continuity damage, self-evolution damage to core modules, and pure-cognitive plugin pollution.
- External constraints must cover physical side effects, blast radius, data exposure, file or remote mutation, monetary cost, compute cost, latency, rollback difficulty, evidence, receipts, read-only probing, sandboxing, dry-run, backup, confirmation, pause, and stop conditions.
- Q6 must read upstream Q3/Q4/Q5 from the persisted nine-question SQLite per-question tables through the authoritative LLM output projection. It must not read legacy response blobs, MongoDB snapshots, or non-SQLite compatibility data.
- Q6 must persist successful question output, LLM output, trace data, context updates, module runs, and module outputs through the split SQLite nine-question tables. These tables must keep schema version and timestamps.
- Q6 must not use fallback, degradation, compatibility, static baseline replacement, or synthesized redline data when Q4 objectives, Q5 compliance results, functional redline execution, global constraints, redline hints, LLM invocation, or LLM output validation fails.
- Q6 must reject malformed, empty, wrong-root, or semantically empty LLM output inside Q6. It must not pass raw or meaningless model output to Q8/Q9 and require downstream cleanup.
- Q6 must keep internal and external lane outputs separate in public methods, context updates, module outputs, logs, and readback helpers.
- On exception, Q6 must raise the error and must not save a Q6 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q6 as a fallback/degraded answer and must not fabricate a new LLM output.
