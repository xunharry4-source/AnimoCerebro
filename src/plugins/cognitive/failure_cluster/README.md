# cognitive_failure_cluster

- Name: Failure Cluster Analyzer
- Description: Group and analyze repeated failure modes.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not query storage-layer relationship tables directly.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into the consolidation `context`.
- This plugin returns `ConsolidationPluginOutput`, not `CognitiveToolResult`.
- Existing output fields that may absorb derived functional-plugin influence are:
  - `promotion_candidates`
  - `compressed_refs`
  - `pattern_scores`

## Contract Limitation

- `ConsolidationPluginOutput` has no dedicated field for preserving raw functional plugin execution evidence.
- If the implementation only needs functional outputs to influence clustering and promotion, the current contract is usable.
- If the implementation must retain original functional plugin results or provenance, extend `ConsolidationPluginOutput` first.
