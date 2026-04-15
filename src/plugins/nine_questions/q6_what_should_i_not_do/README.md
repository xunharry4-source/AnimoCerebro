# nine-question-q6-what-should-i-not-do

- Name: Q6 What Should I Not Do
- Description: Answer the sixth nine-question prompt about forbidden actions and safety boundaries.

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

- Functional plugin outputs must first be merged into Q6's redline inputs.
- Preferred input-side merge targets are:
  - `global_constraints`
  - `redline_hints`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q6_forbidden_zone_profile`

## Constraints

- Functional plugin outputs are redline evidence and scene-specific safety hints.
- Do not create a new top-level Q6 result contract for this feature.
