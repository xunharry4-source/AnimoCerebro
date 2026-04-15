# nine_question_q8_decision

- Name: Q8 What Should I Do Now
- Description: Answer the eighth nine-question prompt about immediate decision making.

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

- Functional plugin outputs must first be merged into Q8's objective-synthesis inputs.
- Preferred input-side merge targets are:
  - `obj_oracles`
  - `objective_catalog`
  - task-priority or queue-shaping inputs derived from `persistent_task_state`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q8_objective_and_queue`
  - `q8_objective_profile`
  - `q8_task_queue`

## Constraints

- Functional plugin outputs must influence prioritization, not bypass Q1-Q7 constraints.
- Do not create a separate top-level Q8 output branch for this feature.
