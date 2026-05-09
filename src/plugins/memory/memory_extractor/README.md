# memory_extractor

- Name: Memory Extractor
- Description: Extract memory candidates from runtime events.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read `plugin_relations` directly from storage and do not bypass the public service boundary.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into this plugin's `model_context`.
- If execution traces or normalized functional inputs need to be preserved, write them under `context_updates["memory_extraction"]`.
- Do not create a parallel top-level result structure outside `memory_extraction` for this feature.

## Constraints

- Keep the plugin fail-closed: missing model provider remains a hard failure.
- Functional plugin outputs are supporting evidence for memory extraction, not a replacement for the plugin's final `CognitiveToolResult`.
