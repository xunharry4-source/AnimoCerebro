# nine-question-q1-where-am-i

- Name: Q1 Where Am I
- Description: Answer the first nine-question prompt about current position and context.

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

- Functional plugin outputs must first be merged into Q1's local sensory aggregation state.
- Preferred input-side merge targets are:
  - `local_inputs["environment_event"]`
  - `local_inputs["physical_host_state"]`
  - `interpretation_markers`
  - `risk_markers`
- If the plugin preserves the derived effect in final outputs, the result must be written through existing Q1 structures:
  - `workspace_domain_inference`
  - `q1_scene_model`
  - `q1_uncertainty_profile`

## Constraints

- Do not introduce a parallel top-level Q1 result tree only for functional plugin results.
- Functional plugin outputs are environment evidence for Q1, not a replacement for Q1's own inference contract.
