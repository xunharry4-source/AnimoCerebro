# 插件启动指南

## 目的

本文档说明一个标准插件如何实现、发现、注册、加载到运行时内存，以及如何启用执行。

本文以 Q2 作为标准示例：

- 插件目录：`src/plugins/nine_questions/q2_asset_inventory`
- 插件 ID：`nine-question-q2-asset-inventory`
- 运行时实现文件：`q2_asset_inventory_plugin.py`
- 工厂函数：`build_q2_asset_inventory_plugin`

## 必须具备的插件结构

标准插件必须是一个独立目录，并且必须包含以下启动文件：

- `startup.py`
- `plugin.json`
- `register.py`
- `README.md`

这些启动文件只负责让插件可发现、可注册。它们不能替代真实运行时实现。

以 Q2 为例，完整插件单元应包含：

- `src/plugins/nine_questions/q2_asset_inventory/startup.py`
- `src/plugins/nine_questions/q2_asset_inventory/plugin.json`
- `src/plugins/nine_questions/q2_asset_inventory/register.py`
- `src/plugins/nine_questions/q2_asset_inventory/README.md`
- `src/plugins/nine_questions/q2_asset_inventory/q2_asset_inventory_plugin.py`
- `src/plugins/nine_questions/q2_asset_inventory/__init__.py`
- Q2 自己拥有的辅助模块，例如 `internal/` 与 `external/`

## 允许的插件路径

插件发现只接受以下两种目录结构：

- `src/plugins/<plugin>`
- `src/plugins/<group>/<plugin>`

Q2 使用第二种结构：

- `src/plugins/nine_questions/q2_asset_inventory`

## 禁止的插件路径

以下嵌套结构无效，不会被注册：

- `src/plugins/<plugin>/<plugin>`

加载器只遍历一级与二级插件目录。更深层目录会被忽略，除非它本身就是上述允许路径中的直接插件单元。

## 实现规则

一个插件分为两层：

- 启动层：`startup.py`、`plugin.json`、`register.py`、`README.md`
- 运行层：真实实现模块，以及通过 `__init__.py` 导出的工厂函数

以 Q2 为例，`__init__.py` 导出 `build_q2_asset_inventory_plugin`，该工厂函数导入真实实现：

- `plugins.nine_questions.q2_asset_inventory.q2_asset_inventory_plugin`

真实实现模块必须定义插件服务可以执行的插件对象。Q2 使用：

- `Q2AssetInventoryPlugin.run_tool(context)`
- 返回 `CognitiveToolResult`

导出的工厂函数必须可以成功 import。如果 `q2_asset_inventory_plugin.py` 缺失，Q2 目录仍可能被发现，但当 `src/zentex/plugins/boot_exports.py` 导入工厂目录时，注册或运行时加载会失败。

## Q2 启动文件示例

Q2 的 `plugin.json` 声明稳定元数据：

```json
{
  "plugin_id": "nine-question-q2-asset-inventory",
  "name": "Q2 我有什么",
  "description": "盘点当前环境中的资产、工具与可执行资源，用于后续权限与行为决策。"
}
```

Q2 的 `startup.py` 负责从工厂目录中解析 `(plugin_id, factory)`：

```python
PLUGIN_ID = "nine-question-q2-asset-inventory"


def startup(factory_catalog: dict[str, object]) -> tuple[str, object]:
    if PLUGIN_ID not in factory_catalog:
        raise KeyError(f"Factory not found for plugin_id={PLUGIN_ID}")
    return PLUGIN_ID, factory_catalog[PLUGIN_ID]
```

Q2 的 `register.py` 暴露同一个插件 ID，并使用相同的工厂解析规则：

```python
PLUGIN_ID = "nine-question-q2-asset-inventory"


def get_plugin_id() -> str:
    return PLUGIN_ID


def resolve_factory(factory_catalog: dict[str, object]) -> object:
    if PLUGIN_ID not in factory_catalog:
        raise KeyError(f"Factory not found for plugin_id={PLUGIN_ID}")
    return factory_catalog[PLUGIN_ID]
```

## 工厂导出规则

每个可发现插件都必须在 `src/zentex/plugins/boot_exports.py` 中导出工厂函数。

以 Q2 为例，`boot_exports.py` 必须导入：

```python
from plugins.nine_questions.q2_asset_inventory import build_q2_asset_inventory_plugin
```

并且 `build_q2_asset_inventory_plugin` 必须出现在 `__all__` 中。

以下位置的插件 ID 必须完全一致：

- `plugin.json`
- `startup.py`
- `register.py`
- `src/zentex/common/plugin_ids.py`
- `src/zentex/plugins/plugin_ids.py`
- 工厂函数创建出的插件对象的 `plugin_id`

Q2 的插件 ID 始终是：

- `nine-question-q2-asset-inventory`

## 独立性规则

插件单元必须自包含。它只能使用：

- 自己插件目录内的文件
- `src/zentex` 下的共享契约与共享服务

插件单元不能依赖另一个插件单元目录内的文件。

以 Q2 为例，`internal/service.py` 与 `external/service.py` 合法，因为它们属于 Q2 插件目录。Q2 也可以调用共享服务，例如：

- `zentex.plugins.service`
- `zentex.common.nine_questions_shared`
- `zentex.common.cognitive_result`

## 注册流程

注册是显式动作。发现插件目录并不会自动把插件写入插件数据库。

标准流程如下：

1. 实现运行时插件对象与工厂函数。
2. 在 `src/zentex/plugins/boot_exports.py` 导出工厂函数。
3. 在允许路径下创建插件目录。
4. 添加 `startup.py`、`plugin.json`、`register.py`、`README.md`。
5. 确保 `startup.py` 可以从工厂目录解析 `(plugin_id, factory)`。
6. 当插件需要写入插件存储时，调用插件服务的注册 API。

推荐使用的公开 API：

- `register_discovered_plugins(service)`
  - 发现插件目录，并把缺失插件注册到存储中。
- `rehydrate_registered_plugins(service)`
  - 把已经注册的插件从存储加载到运行时内存。
- `ensure_default_plugin_relationships(service)`
  - 显式初始化内置默认关系。

`service.bootstrap()` 仍然作为旧的组合入口存在，但新调用方应优先使用上面的显式注册与显式加载 API。

## 启用规则

注册和启用不是一回事。

- 已注册：插件元数据存在于插件存储中。
- 已加载：注册过的插件实例已经加载到运行时内存。
- 已启用：插件允许被执行。

插件要能执行，通常必须同时满足：

- `lifecycle_status` 是 active。
- `operational_status` 是 enabled。
- 插件实例可以通过导出的工厂函数加载。
- 调用方走插件服务执行路径，而不是直接临时 import 插件实现。

以 Q2 为例，工厂函数创建出的插件对象应暴露：

- `plugin_id = "nine-question-q2-asset-inventory"`
- `feature_code = "nine_questions.q2"`
- `behavior_key = "nine_questions"`
- `lifecycle_status = "active"`
- `operational_status = "enabled"`

## 发现、注册、执行的区别

这些是独立阶段：

- 发现：
  - 扫描 `src/plugins` 下的插件单元目录。
  - 调用 `startup.py` 解析 `(plugin_id, factory)`。
- 注册：
  - 将插件元数据写入插件存储或数据库。
  - 必须由 plugins 模块显式触发。
- 加载：
  - 从工厂函数创建已注册插件实例，并放入运行时内存。
- 执行：
  - 通过插件服务调用已加载插件。

Q2 的预期执行路径是：

1. `boot_exports.py` 导入 `build_q2_asset_inventory_plugin`。
2. 插件发现看到 `src/plugins/nine_questions/q2_asset_inventory`。
3. `startup.py` 将 `nine-question-q2-asset-inventory` 解析到工厂函数。
4. 注册流程写入 Q2 元数据。
5. 加载流程创建 `Q2AssetInventoryPlugin`。
6. 执行流程调用 `Q2AssetInventoryPlugin.run_tool(context)`。

## 加载器入口

插件加载器入口是：

- `src/plugins/startup.py`

主要 API：

- `discover_plugin_unit_directories()`
- `resolve_registry_factories(factory_catalog)`
- `bootstrap_plugins(db_path)`

## 架构约束

- `launcher` 的正常启动链不得隐式执行插件发现或插件注册。
- 如果系统需要发现或注册插件，该工作必须属于 plugins 模块自身，并通过 `zentex.plugins.service` 完成。
