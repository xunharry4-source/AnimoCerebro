# nine_question_q9_action_plan

- Name: Q9 How Should I Act
- Description: Answer the ninth nine-question prompt by producing a concrete ten-field ActionPlan.

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

- Functional plugin outputs must first be merged into Q9's action-planning inputs.
- Preferred input-side merge targets are:
  - `posture_oracles`
  - `posture_catalog`
- Final LLM output must be reflected through:
  - `q9_action_plan`
- Compatibility projections may still be exposed for downstream task overlays through:
  - `q9_evaluation_profile`
  - `q9_evolution_profile`
  - `q9_escalation_profile`

## Constraints

- Functional plugin outputs are action-planning evidence and must not bypass the final Q8 decision context.
- Q9 must read authoritative Q1-Q8 LLM outputs from the SQLite nine-question snapshot tables before ActionPlan synthesis.
- Q9 requires completed Q1-Q8 upstream snapshots, real self-model input, real reasoning budget input, and at least one successful posture plugin result.
- Q9 must persist only its own successful module outputs into the SQLite module-output tables.
- Q9 must persist functional posture evidence, Q1-Q8 validation, self-model validation, reasoning-budget validation, posture baseline, and LLM ActionPlan projection as separate module records.
- Every persisted Q9 table row is versioned and timestamped by the shared SQLite nine-question store.
- Q9 must not return substitute, legacy, or incomplete responses. Exceptions propagate and failed exception payloads are not saved.
