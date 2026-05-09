# cognitive_expired_assumption

- Name: Expired Assumption Cleaner
- Description: Detect and clean stale assumptions.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly from storage.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into the consolidation `context`.
- This plugin returns `ConsolidationPluginOutput`, not `CognitiveToolResult`.
- With the current contract, the only stable built-in write location is the pruning decision itself, surfaced through `ConsolidationPluginOutput.pruned_refs`.

## Contract Limitation

- `ConsolidationPluginOutput` currently contains only:
  - `promotion_candidates`
  - `pruned_refs`
  - `compressed_refs`
  - `pattern_scores`
- It does not currently provide a dedicated metadata or audit-evidence field for preserving raw functional plugin outputs.
- If functional plugin execution evidence must be retained explicitly, extend `ConsolidationPluginOutput` first before implementing this expansion.
