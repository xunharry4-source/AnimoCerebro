# cognitive_semantic_conflict

- Name: Semantic Conflict Checker
- Description: Detect semantic conflicts in plans and outputs.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not access storage-layer relationship data directly.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into the semantic conflict inference `context` sent to the model provider.
- This plugin returns `CognitiveConflictReport`, not `CognitiveToolResult`.
- Functional plugin evidence must therefore be written into `CognitiveConflictReport.details`.
- Do not add separate top-level output branches for functional plugin results.

## Constraints

- The model-driven semantic judgment remains the primary decision point.
- Functional plugin outputs are supporting evidence for semantic conflict detection and auditability.
