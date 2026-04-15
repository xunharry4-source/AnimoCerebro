# nine_question_q7_alternatives

- Name: Q7 What Else Can I Do
- Description: Answer the seventh nine-question prompt about alternatives and options.

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

- Functional plugin outputs must first be merged into Q7's alternative-strategy inputs.
- Preferred input-side merge targets are:
  - `alt_oracles`
  - `alternative_catalog`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q7_alternative_strategy_profile`

## Constraints

- Functional plugin outputs are fallback-strategy evidence, not a replacement for Q7's synthesized alternative profile.
- Do not create a separate top-level Q7 output branch for this feature.
