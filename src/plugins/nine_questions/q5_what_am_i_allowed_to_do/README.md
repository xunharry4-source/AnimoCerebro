# nine-question-q5-what-am-i-allowed-to-do

- Name: Q5 What Am I Allowed To Do
- Description: Answer the fifth nine-question prompt about allowed actions and limits.

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

- Functional plugin outputs must first be merged into Q5's authorization inputs.
- Preferred input-side merge targets are:
  - `model_context["contact_policy"]`
  - `model_context["tenant_scope"]`
  - `model_context["agent_trust_policy"]`
  - Q4-derived actionable-space cropping inputs where applicable
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q5_authorization_boundary_profile`

## Constraints

- Functional plugin outputs must narrow or explain authorization boundaries; they must not widen them beyond Q4.
- Do not create a separate top-level Q5 output branch for functional plugin results.
