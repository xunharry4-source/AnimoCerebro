# nine-question-q6-what-should-i-not-do

- Name: Q6 What If I Do It
- Description: Answer the sixth nine-question prompt about the cost, consequence, reversibility, mitigation, and stop conditions of doing an action.

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

- Functional plugin outputs must first be merged into Q6's consequence and boundary inputs.
- Preferred input-side merge targets are:
  - `global_constraints`
  - `redline_hints`
- If the plugin preserves the derived forbidden-zone effect for downstream compatibility, the result may also be reflected through:
  - `q6_forbidden_zone_profile`

## Constraints

- Functional plugin outputs are consequence evidence and scene-specific safety hints.
- Q6 LLM output must use the strict top-level `ConsequenceAssessment` and `CostImpactProfile` contract.
- Q6 must read upstream Q3/Q4/Q5 from the persisted nine-question SQLite per-question tables through the authoritative LLM output projection. It must not read legacy response blobs, MongoDB snapshots, or non-SQLite compatibility data.
- Q6 must persist successful question output, LLM output, trace data, context updates, module runs, and module outputs through the split SQLite nine-question tables. These tables must keep schema version and timestamps.
- Q6 must not use fallback, degradation, compatibility, static baseline replacement, or synthesized redline data when Q4 boundary, Q5 authorization boundary, functional redline execution, global constraints, redline hints, LLM invocation, or LLM output validation fails.
- On exception, Q6 must raise the error and must not save a Q6 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q6 as a fallback/degraded answer and must not fabricate a new LLM output.
