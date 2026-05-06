# nine-question-q5-what-am-i-allowed-to-do

- Name: Q5 What Can I Not Do
- Description: Answer the fifth nine-question prompt about forbidden, unauthorized, and escalation-required actions.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public service boundary.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into Q5's cannot-do boundary inputs.
- Preferred input-side merge targets are:
  - `model_context["contact_policy"]`
  - `model_context["tenant_scope"]`
  - `model_context["agent_trust_policy"]`
  - Q4-derived actionable-space cropping inputs where applicable
- The canonical live-LLM result is still `AuthorizationBoundary`, but its business meaning is the Q5 cannot-do boundary. It is persisted as:
  - `authorization_boundary`
  - `q5_authorization_boundary`
- Q5 also projects the canonical boundary plus validated policy baseline into downstream structures required by Q6/Q8/Q9:
  - `q5_authorization_boundary_profile`
  - `q5_permission_boundary`
  - `q5_objective_convergence_guard`

## Constraints

- Functional plugin outputs must narrow or explain cannot-do boundaries; they must not widen allowed action space beyond Q4.
- Q5 live LLM output must be strict JSON and must contain exactly one root object key, `AuthorizationBoundary`, with:
  - `current_authorization_scope`
  - `communication_policy`
  - `organizational_boundary`
  - `allowed_operations`
  - `forbidden_operations`
- `forbidden_operations` is the primary Q5 answer. `allowed_operations` must be a subset of Q4 `actionable_space` and only serves as an audited comparison set. Any LLM output that exceeds Q4 must fail closed.
- Q8 must shrink objectives to single-brain achievable goals when `q5_objective_convergence_guard.objective_scope` is `single_brain_only`, collaboration is unavailable, or authorization is limited.
- Q9 must treat `forbidden_operations` as authorization red lines for posture, escalation, and dispatch.
- The prompt assembly must persist `system_prompt`, injected evidence context, raw response, token usage, and `question_driver_refs` in `llm_trace_payload`.
- Q5 must read upstream Q3/Q4 and policy inputs from the persisted nine-question SQLite per-question tables through the authoritative LLM output projection. It must not read legacy response blobs, MongoDB snapshots, or non-SQLite compatibility data.
- Q5 must persist successful question output, LLM output, trace data, context updates, module runs, and module outputs through the split SQLite nine-question tables. These tables must keep schema version and timestamps.
- Q5 must not use fallback, degradation, compatibility, synthesized policy, or snapshot-only replacement data when Q4 boundary, tenant scope, contact policy, agent trust policy, functional authorization execution, LLM invocation, LLM output validation, or authorization guard validation fails.
- On exception, Q5 must raise the error and must not save a Q5 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q5 as a fallback/degraded answer and must not fabricate a new LLM output.
