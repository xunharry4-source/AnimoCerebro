# nine_question_q9_posture

- Name: Q9 How Should I Act
- Description: Answer the ninth nine-question prompt about posture and action.

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

- Functional plugin outputs must first be merged into Q9's posture-synthesis inputs.
- Preferred input-side merge targets are:
  - `posture_oracles`
  - `posture_catalog`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q9_evaluation_profile`
  - `q9_evolution_profile`
  - `q9_escalation_profile`

## Constraints

- Functional plugin outputs are posture-control evidence and must not bypass the final Q8 decision context.
- Do not create a separate top-level Q9 output branch for this feature.
