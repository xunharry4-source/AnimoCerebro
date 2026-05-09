# cognitive_budget_conflict

- Name: Budget Conflict Checker
- Description: Detect budget and resource allocation conflicts.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public plugin service.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into the conflict detection `context`.
- This plugin returns `CognitiveConflictReport`, not `CognitiveToolResult`.
- Functional plugin evidence must therefore be written into `CognitiveConflictReport.details`.
- Do not introduce `context_updates`-style result fields for this plugin.

## Constraints

- The canonical conflict output remains `conflict_type`, `severity`, `suggested_resolution`, and `details`.
- Functional plugin outputs are admissible only as audit evidence or budget-evaluation inputs.
