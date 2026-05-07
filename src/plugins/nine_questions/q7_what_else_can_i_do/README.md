# nine-question-q7-what-else-can-i-do

- Name: Q7 What Else Can I Do
- Description: Explore additional internal and external possibilities beyond the current Q4/Q5/Q6 path, without turning those discoveries into executable objectives until they return through Q4, Q5, and Q6.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Product Semantics

Q7 answers: 创造性探索 / 我还能干什么。

Q7 is Zentex's creativity center. It breaks the linear "problem -> solution" chain and introduces "problem -> exploration -> decision" thinking. Q7 asks what else could be possible after Q4 has generated objectives, Q5 has filtered compliance, and Q6 has added plan constraints.

Q7 is not a red-line page. It does not decide what is forbidden, allowed, compliant, costly, or executable:

- Q5 owns hard blocks, red lines, permission boundaries, platform abuse, and protected module boundaries.
- Q6 owns plan constraints, consequences, rationality, rollback, pause, and stop conditions.
New executable objectives discovered by Q7 must return to Q4 as objective candidates, then pass Q5 compliance and Q6 plan constraints before any execution path can use them.

## Internal Lane Documentation

The Q7 internal plugin is the internal `CreativePossibilitySet` producer. It explores additional internal possibilities beyond the current Q4/Q5/Q6 path without turning those possibilities into authorized objectives.

Its responsibility is to generate non-linear internal possibility seeds for reflection, learning, memory architecture, value prompting, self-evolution experiments, pure cognitive plugin ideas, and low-cost internal experiments.

Internal inputs:

- `Q4_InternalObjectiveCandidates`
- `Q5安全规则包`
- `Q5 candidate_safety_rule_bindings`
- `Q6限制与后果`
- `LivingSelfModel_Snapshot`
- `Reflection_CapabilityGapSignal_Internal`
- current problem summary, long-term goal summary, historical successes, historical failures, and learnable tool signals when available

Internal output root:

- `InternalCreativePossibilitySet`

Internal output must include `creative_possibilities`, and each possibility must include:

- `category`
- `description`
- `rationale`
- `possibility_status`

Allowed internal categories:

- `alternative_internal_objectives`
- `new_reasoning_paths`
- `new_reflection_methods`
- `new_memory_architecture_options`
- `value_prompting_possibilities`
- `learning_opportunities`
- `self_evolution_possibilities`
- `pure_cognitive_plugin_ideas`
- `low_cost_internal_experiments`

Allowed possibility statuses:

- `hypothetical`
- `needs_discovery`
- `needs_learning`
- `needs_verification`
- `needs_authorization`
- `ready_for_q4_objective_candidate`

Internal Q7 must not output `Q7InternalRedLineAssessment`, red-line hits, non-bypassable constraints, execution plans, task IDs, external tool parameters, or Markdown. Even `ready_for_q4_objective_candidate` is only a return-to-Q4 hint; it is not execution permission and must still pass Q5 and Q6.

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public service boundary.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.
- Functional plugin outputs are discovery hints, learning opportunities, collaboration options, tool options, and low-risk probe candidates. They must not be presented as already authorized or executable capabilities unless Q4/Q5/Q6 later prove that state.

## Input Semantics

Q7 may consume:

- Q1 environment objective signals.
- Q2 self-observation objective signals and asset gaps.
- Q3 identity hypotheses.
- Q4 objective candidates and capability evidence.
- Q5 `GoalComplianceAssessment` and `SystemSafetyBoundary`.
- Q6 `PlanConstraintSet` and `ConsequenceAndRationalityAssessment`.
- Functional alternatives, tool-learning opportunities, connector discovery hints, collaboration opportunities, and public environment signals.
- Compatibility projections such as `q7_alternative_strategy_profile`, `q5_authorization_boundary_profile`, `q6_forbidden_zone_profile`, and redline hints only as old-session evidence or safety context.

Q7 must not use downstream results to rewrite creative exploration.

## Write Locations

- Functional plugin outputs must first be merged into Q7's creative possibility evidence inputs.
- Preferred input-side merge targets are:
  - `model_context["q1_environment_objective_signal_set"]`
  - `model_context["q2_self_observation_objective_signal_set"]`
  - `model_context["q3_identity_hypothesis_set"]`
  - `model_context["q4_objective_candidate_set"]`
  - `model_context["q5_goal_compliance_assessment"]`
  - `model_context["q5_system_safety_boundary"]`
  - `model_context["q6_plan_constraints"]`
  - `model_context["q6_consequence_and_rationality_assessment"]`
  - `model_context["functional_alternatives"]`
  - `model_context["tool_learning_opportunities"]`
  - `model_context["connector_discovery_hints"]`
  - `model_context["collaboration_opportunities"]`
  - `model_context["public_environment_signals"]`
- The canonical product result is `CreativePossibilitySet` plus `BeyondCurrentPossibilitySet`.
- Q7 must persist or project the canonical result into:
  - `q7_creative_possibility_set`
  - `q7_beyond_current_possibility_set`
  - `q7_internal_creative_possibilities`
  - `q7_external_creative_possibilities`
  - `q7_possibility_statuses`
  - `q7_q4_return_candidate_hints`
  - `q7_low_risk_probe_candidates`
  - `q7_tool_learning_opportunities`
  - `q7_collaboration_opportunities`
- Legacy read models may still be persisted for compatibility and display:
  - `q7_alternative_strategy_profile`
  - `q7_functional_alternatives`
  - `q7_alternative_strategy_baseline`
  - `q7_resource_bottlenecks`
  - `q7_capability_limits`
  - `q7_permission_boundaries`
  - `q7_absolute_red_lines`

Legacy alternative-strategy and red-line fields are compatibility projections. They must not replace the Q7 product semantic of creative possibility exploration.

## Output Semantics

Each possibility must include:

- `possibility_id`
- `lane`
- `possibility_status`
- `possibility_description`
- `source_refs`
- `q5_boundary_refs`
- `q6_constraint_refs`
- `q4_return_candidate_hint`

The internal cognition lane returns `InternalCreativePossibilitySet` with:

- `alternative_internal_objectives`
- `new_reasoning_paths`
- `new_reflection_methods`
- `new_memory_architecture_options`
- `value_prompting_possibilities`
- `learning_opportunities`
- `self_evolution_possibilities`
- `pure_cognitive_plugin_ideas`
- `low_cost_internal_experiments`

The external execution lane returns `ExternalCreativePossibilitySet` with:

- `public_competitor_signal_research`
- `content_quality_opportunities`
- `subreddit_rule_learning`
- `authorized_account_compliance_audit`
- `unregistered_agent_options`
- `unknown_cli_options`
- `new_mcp_server_options`
- `new_connector_options`
- `browser_or_saas_automation_options`
- `external_service_options`
- `collaboration_opportunities`
- `tool_learning_opportunities`
- `low_risk_probe_candidates`

## Public Method Contract

Q7 exposes internal and external creative possibility results through two separate public method families. Callers must choose the correct scope explicitly. Q7 must not return a combined internal/external payload, and downstream modules must not be responsible for cleaning raw LLM garbage.

### Internal scope

- `normalize_q7_internal_creative_possibility_set(llm_output: dict) -> dict`
  - Accepts a raw internal Q7 LLM output.
  - Requires `type="InternalCreativePossibilitySet"` and a non-empty `creative_possibilities` list.
  - Validates each possibility category and `possibility_status`.
  - Rejects macro-variable leakage such as `{{...}}`.
- `build_q7_internal_context_updates(internal: dict) -> dict`
  - Returns only internal context update keys:
    - `q7_internal_creative_possibility_set`
    - `q7_internal_creative_possibilities`
    - `q7_internal_possibility_statuses`
    - `q7_internal_ready_for_q4_objective_candidates`
- `load_internal_llm_output_from_table(db_path=None, session_id="nq-baseline") -> dict`
  - Reads only module row `q7_internal_creativity_llm`.
  - Returns the normalized internal creative possibility set, not the raw LLM wrapper.

### External scope

- `normalize_q7_external_creative_possibility_set(llm_output: dict) -> dict`
  - Accepts a raw external Q7 LLM output.
  - Requires `type="ExternalCreativePossibilitySet"` and at least 3 creative possibilities.
  - Validates each `possibility_type` and `possibility_status`.
  - Rejects macro-variable leakage such as `{{...}}`.
  - Rejects platform abuse patterns such as governance bypass, fingerprint bypass, vote manipulation, ban evasion, sockpuppet behavior, or bulk abuse.
- `build_q7_external_context_updates(external: dict) -> dict`
  - Returns only external context update keys:
    - `q7_external_creative_possibility_set`
    - `q7_external_creative_possibilities`
    - `q7_external_possibility_statuses`
    - `q7_external_ready_for_q4_objective_candidates`
    - `q7_external_needs_registration_possibilities`
- `load_external_llm_output_from_table(db_path=None, session_id="nq-baseline") -> dict`
  - Reads only module row `q7_external_creativity_llm`.
  - Returns the normalized external creative possibility set, not the raw LLM wrapper.

### Forbidden public surface

- `load_llm_output_from_table(...)` is intentionally forbidden and must raise `q7_combined_llm_output_forbidden`.
- `Q7WhatElseCanIDoPlugin.run_tool(...)` must not expose `q7_red_line_assessment` or any other merged internal/external output key.
- Q7 must not return unrecognized raw LLM payloads as a successful result. Bad shape, missing required fields, or failed validation must fail inside Q7 before the result reaches web projection or task-center code.
- Internal fields must stay under `q7_internal_*`; external fields must stay under `q7_external_*`.

## Candidate Status

Each candidate must set `possibility_status` to one of:

- `hypothetical`
- `needs_discovery`
- `needs_learning`
- `needs_registration`
- `needs_verification`
- `needs_authorization`
- `ready_for_q4_objective_candidate`

Only `ready_for_q4_objective_candidate` may be projected as a Q4-return candidate hint. It still cannot enter execution directly.

## Social Platform Boundary

Q7 may suggest compliant exploration such as:

- Public competitor signal research based on publicly accessible content and public community rules.
- Content quality opportunities around unanswered questions, format gaps, title quality, summaries, or media quality.
- Subreddit rule learning from public rules, wikis, pinned posts, posting formats, and self-promotion limits.
- Authorized account compliance audits for repeated posts, vote mixing, cadence, and self-promotion boundaries.
- Tool-learning opportunities such as Reddit API clients, public-data analyzers, rule parsers, content quality scorers, or human review panels.

Q7 must not suggest platform governance evasion, vote manipulation, ban evasion, coordinated sockpuppet behavior, fingerprint bypass, private-data scraping, API-limit bypass, or other abuse paths. Those belong to Q5 hard-blocking, not Q7 exploration.

## Constraints

- Q7 LLM output must be strict JSON and must validate as Q7 creative possibility output.
- Q7 must use live LLM for non-linear possibility exploration. Static rules may provide safety boundaries and output shape, but must not replace creative exploration.
- Q7 must not present unregistered agents, unknown CLI tools, new MCP servers, new connectors, browser/SaaS automations, or external services as current executable capabilities.
- Q7 must not bypass Q5 `hard_blocked` decisions or downgrade Q6 constraints.
- Q7 executable discoveries must return to Q4 for objective expression, then pass Q5 and Q6 before execution.
- Q7 must receive upstream Q1/Q2/Q3/Q4/Q5/Q6 content through upstream-owned public read methods and pass that content directly into its LLM request. It must not read legacy response blobs, MongoDB snapshots, or non-SQLite compatibility data.
- Q7 must persist successful question output, LLM output, trace data, context updates, module runs, and module outputs through the split SQLite nine-question tables. These tables must keep schema version and timestamps.
- Q7 must not use fallback, degradation, compatibility, static baseline replacement, or synthesized redline data when upstream context, functional discovery, LLM invocation, or LLM output validation fails.
- On exception, Q7 must raise the error and must not save a Q7 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q7 as a fallback/degraded answer and must not fabricate a new LLM output.
