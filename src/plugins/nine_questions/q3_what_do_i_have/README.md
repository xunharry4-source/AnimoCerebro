# nine-question-q3-what-do-i-have

- Name: Q3 What Do I Have
- Description: Answer the third nine-question prompt about available assets and capabilities.

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

- Functional plugin outputs must first be merged into Q3's asset inventory inputs.
- Preferred input-side merge targets are:
  - `cognitive_tool_registry`
  - `execution_domain_registry`
  - `connected_agent_catalog`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through existing Q3 structures:
  - `q3_unified_asset_inventory`
  - `q3_resource_evaluation`
  - `q3_humanized_asset_inventory`

## Constraints

- Functional plugin outputs must support asset inventory and resource evaluation semantics.
- Do not create a new top-level Q3 result contract for this feature.
