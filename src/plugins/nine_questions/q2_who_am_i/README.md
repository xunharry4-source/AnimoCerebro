# nine-question-q2-who-am-i

- Name: Q2 Who Am I
- Description: Answer the second nine-question prompt about identity and role.

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

- Functional plugin outputs must first be merged into Q2's identity inference inputs.
- Preferred input-side merge targets are:
  - `role_payload`
  - `constraint_payload`
  - `risk_weight`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through existing Q2 structures:
  - `q2_role_profile`
  - `q2_mission_boundary`

## Constraints

- Do not create a separate top-level result branch for functional plugin outputs.
- Functional plugin outputs are identity and constraint inputs for Q2's role inference.
