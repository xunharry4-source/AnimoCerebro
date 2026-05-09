# nine-question-q2-asset-inventory

- Name: Q2 我有什么
- Product semantics: 盘点并汇总当前系统工具、协同智能体、记忆和可复用策略补丁，生成供 Q3 角色推断使用的运行时资产画像。

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Plugin Inventory Rules

- This cognitive plugin must query all plugin metadata only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public service boundary.
- Do not execute Q2-bound enabled functional plugins as an asset expansion path.
- Query the canonical all-plugin inventory with `query_all_plugins_by_lifecycle(...)` and persist it under `q2_plugin_service_inventory`.

## Runtime Write Locations

- Canonical plugin service query results are merged into Q2 “我有什么”输入侧，优先写入：
  - `q2_plugin_service_inventory`
  - `cognitive_tool_registry`
  - `execution_domain_registry`
- Q2 我有什么结果主要写入：
  - `q2_asset_inventory`
  - `q2_resource_evaluation`
  - `q2_unified_asset_inventory`
  - `q2_plugin_service_inventory`
- `q2_asset_inventory` 由 `AssetInventory` 结构定义，需包含:
  - `inventory_summary`
  - `long_term_memory`
  - `cognitive_and_functional_tools`
  - `connected_agents`
  - `strategy_patches`

## Constraints

- Do not create or execute a Q2-bound enabled functional plugin expansion path.
- All plugin metadata must come from the canonical plugin service query result.
- Workspace files and host permission inventory belong to Q1 and must not be re-emitted by the Q2 AssetInventory LLM contract.
- Q2 must not infer or write `active_role`; role inference belongs only to Q3.
