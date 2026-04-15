# reflection_generator

- Name: Reflection Generator
- Description: Generate reflection and learning-oriented summaries.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not query storage tables directly and do not call functional plugins outside the public plugin service.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into this plugin's `model_context`.
- If the plugin needs to preserve normalized functional evidence, store it under `context_updates["reflection"]`.
- Do not create a separate top-level reflection result branch just for functional plugin data.

## Constraints

- Reflection generation remains LLM-backed and fail-closed.
- Functional plugin outputs are additional reflection evidence and must not weaken the existing `reflection` output contract.
