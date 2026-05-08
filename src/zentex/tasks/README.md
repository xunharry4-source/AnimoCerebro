# Tasks Module / 任务模块

## Overview / 概述

`zentex.tasks` 是系统的统一任务管理层，负责：

- 任务创建、状态流转、依赖管理
- mission 拆解与分发
- 统一任务查询与持久化
- 对 `reflection`、`upgrade` 等外部工作流提供统一托管入口

当前真实核心实现：

- [management/task_management_service.py](management/task_management_service.py)
- [service.py](service.py) 仅保留稳定导出接口，不允许新增业务逻辑
- [__init__.py](__init__.py)
- [core/interface.py](core/interface.py)
- [integration/workflow_bridge.py](integration/workflow_bridge.py)

维护者目录与文件职责索引：

- [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)

## Current Entry Points / 当前入口

对外主要入口是：

- `TaskManagementService`
- `TaskManager`
- `TaskServiceInterface`

其中：

- `TaskManagementService` 是底层真实状态机和持久化边界
- `TaskManager` 是高层便利封装
- `TaskServiceInterface` 是给外部模块和 Web/API 用的安全接口层

## Current Capabilities / 当前能力

### 1. Task Lifecycle / 任务生命周期

任务状态模型定义在 [models/models.py](models/models.py)：

- `TODO`
- `IN_PROGRESS`
- `BLOCKED`
- `WAITING_CONFIRMATION`
- `SUSPENDED`
- `DONE`
- `FAILED`
- `ARCHIVED`

状态流转由 [management/task_management_service.py](management/task_management_service.py) 强校验，不允许非法跳转。

### 2. Query and Filtering / 查询与过滤

`list_tasks()` 现在支持：

- `status`
- `priority`
- `tags`
- `parent_task_id`
- `target_id`
- `overdue_only`
- `source_module`
- `metadata_filters`

这意味着统一任务管理现在可以直接筛出：

- `source_module="reflection"`
- `source_module="upgrade"`

而不需要上层自己扫描全部任务。

### 3. Workflow Integration / 工作流集成

[integration/workflow_bridge.py](integration/workflow_bridge.py) 负责把外部工作流同步成标准任务。

当前已接入：

- `reflection.async_service`
- `upgrade.execution`

桥接后会写入统一任务 metadata，例如：

- `source_module`
- `workflow_kind`
- `workflow_status`
- `workflow_progress`
- `upgrade_action`
- `upgrade_target_kind`

### 4. Metadata Tracking / 元数据跟踪

[management/task_management_service.py](management/task_management_service.py) 已提供 `update_task_metadata()`，用于在不改变状态机语义的前提下，持续写入工作流阶段数据。

这一步是后续控制台展示 `reflection / upgrade` 阶段细节的基础。

### 5. Task Decomposition and Executor Assignment / 任务分解与执行方分配

**任务分解与执行方来源规则：**

对于 Mission 分解生成的子任务，执行方必须来自以下注册表之一：

**内部任务 / Internal Tasks:**
- 执行方必须在 `src/zentex/plugins` 内部插件中注册
- 执行方 ID 格式：`internal:<plugin_name>`
- 来源：`PluginService.get_plugins()` 或内部插件 registry

**外部任务 / External Tasks:**
- **CLI 工具**：`src/zentex/cli` 中存在的命令工具
  - 执行方 ID 格式：`cli:<tool_name>`
  - 来源：`CLIService.list_tools()`
  
- **MCP 服务器**：`src/zentex/mcp` 中注册的 MCP 服务器
  - 执行方 ID 格式：`mcp:<server_name>`
  - 来源：`MCPService.list_servers()`
  
- **Agent**：`src/zentex/agents` 中定义的代理
  - 执行方 ID 格式：`agent:<agent_name>`
  - 来源：`AgentService` 或 agent registry
  
- **外接功能 / External Connectors**：第三方集成
  - 执行方 ID 格式：`external_connector:<connector_name>`
  - 来源：`ExternalConnectorService`

**当前验证状态 / Current Validation Status:**

✅ **已实现执行方来源约束与存在性验证**

当前系统在子任务分配阶段已启用以下校验：

1. **范围约束**：
  - `task_scope=internal` 仅允许匹配 `internal:*`（内部插件）
  - `task_scope=external` 仅允许匹配 `cli:*` / `mcp:*` / `agent:*` / `external_connector:*`
2. **存在性校验**：
  - 对 `required_resources` 中显式执行方引用（如 `执行方钦定：...`）进行真实注册表匹配
  - 若执行方不存在，进入 `resource_gap` 并挂起，不会进入执行队列
3. **分配成功后才入执行队列**：
  - 状态由 `assignment_pending -> queued`
  - 同时写入 `worker_dispatch_enabled=true`，允许 worker 拉取执行
4. **Q9 子任务生成后合规复核**：
  - 子任务列表生成后会执行 `validate_q9_subtask_splitting_against_llm_output` 复核
  - 复核维度包含：Q9 目标一致性、执行方真实性与存在性、验收/验证方式是否为可审计物理证据、任务颗粒度
  - 若复核失败：新建子任务会被取消，父任务标记失败，并写入 `q9_subtask_splitting_validation`
  - 若复核通过：子任务 metadata 写入 `q9_subtask_validation.status=passed`

## LLM Prompt Structure / LLM 提问结构

任务模块内的 LLM 提问已经从执行器中拆出，不再允许在业务文件里内联大段 prompt。

当前关键文件：

- [core/simple_llm_prompt.py](core/simple_llm_prompt.py)
- [core/semantic_kernel_llm_prompt.py](core/semantic_kernel_llm_prompt.py)
- [verification/llm_prompt.py](verification/llm_prompt.py)

这些 builder 已统一支持 section 化输出：

- `system_prompt`
- `prompt`
- `system_prompt_sections`
- `prompt_sections`

每个 section 至少包含：

- `key`
- `title`
- `intent`
- `purpose`
- `content`

## Prompt Upgrade Contracts / Prompt 升级合同

任务模块的 prompt 升级合同不再散落在各文件中，而是按模块 service 暴露：

- [core/service.py](core/service.py)
- [verification/service.py](verification/service.py)

合同使用 [common/prompt_upgrade_contract.py](../common/prompt_upgrade_contract.py)，明确声明：

- `immutable_intent`
- `editable_prompt_sections`
- `immutable_prompt_sections`
- `section_change_policy`
- `allowed_prompt_change_scope`
- `forbidden_prompt_changes`

## Persistence / 持久化

任务模块支持两种运行形态：

- 数据库模式
- 本地共享状态回退模式

数据库启用时，底层由 DAO 层负责持久化。  
统一查询与状态机仍由 `TaskManagementService` 控制，不允许外部直接绕过服务写库。

## Integration Contract / 集成边界

其他模块接入任务系统时，必须遵守：

- 不直接写任务内部共享状态
- 不直接操作 DAO 或数据库表
- 统一通过 `TaskManagementService` / `TaskServiceInterface`
- 工作流同步统一经由 `WorkflowTaskBridge`

当前推荐模式：

1. 外部模块保留自己的内部队列或管理账本
2. 同时把关键生命周期同步进 `zentex.tasks`
3. 在 `metadata` 中保留模块来源和阶段信息

## Executor Registry and Validation / 执行方注册表与验证

### Executor Sources / 执行方来源

系统支持以下执行方注册表：

| 执行方类型 | 来源路径 | 查询服务 | ID 前缀 |
|-----------|--------|--------|--------|
| Internal Plugin | `src/zentex/plugins` | `PluginService.get_plugins()` | `internal:` |
| CLI Tool | `src/zentex/cli` | `CLIService.list_tools()` | `cli:` |
| MCP Server | `src/zentex/mcp` | `MCPService.list_servers()` | `mcp:` |
| Agent | `src/zentex/agents` | `AgentService` | `agent:` |
| External Connector | `src/zentex/external_connectors` | `ExternalConnectorService` | `external_connector:` |

### Validation Mechanism / 验证机制

当前验证机制已在分配链路生效：

1. **Assignment Gate Routing** (分配闸门路由)
  - Mission 子任务创建后进入 `assignment_pending`
  - 通过 `TaskAssignmentRouter.route_assignment_pending_task()` 进入统一分配闸门

2. **Scope-Aware Registry Lookup** (按任务范围查询注册表)
  - 内部任务只查内部插件注册表
  - 外部任务只查 CLI/MCP/Agent/External Connector 注册表

3. **Owner Reference Validation** (执行方引用校验)
  - 对 `required_resources` 中执行方钦定引用进行标准化与匹配
  - 不存在时返回 `resource_gap`，并触发挂起与恢复条件记录

4. **Health and Availability Check** (健康与可用性检查)
  - MCP 执行方要求在线且健康
  - External Connector 执行方要求 active 且 health_check 通过
  - Agent 执行方要求来自 active agents 列表

5. **Recovery Loop** (恢复闭环)
  - `resource_gap` 任务进入 `suspended`
  - 调度器周期运行时尝试自动恢复并重新分配

6. **Post-Generation Compliance Validation** (生成后合规验证)
  - Q9 子任务在创建并完成执行方分配后，会与 Q9 action blueprint 做一致性校验
  - 校验执行方是否在 Available Tools Registry 中真实存在，且符合 internal/external 计划类型
  - 校验 `acceptance_criteria` 是否继承 Q9 `verification_method`，并满足零信任物理证据要求
  - 任何维度不合规都会阻断后续执行链路，避免错误子任务进入运行态

## Runtime Closure Status / 运行态闭环状态

当前任务闭环状态：

- ✅ **分解 -> 分配 -> 入队**：已连通
- ✅ **Q9 输出一致性复核（含执行方与达成条件）**：已连通
- ✅ **待执行任务自动派发**：已连通（`queued/todo` + `worker_dispatch_enabled=true`）
- ✅ **资源缺口自动恢复重试**：已连通（调度器周期检查）
- ✅ **超时任务回收与重发**：已连通

运行前置条件：

1. `TaskAutoLoopScheduler` 必须启动（默认启用）
2. 外部执行方（CLI/MCP/Agent/Connector）在运行时必须可查询且健康
3. 被人工审批策略拦截的任务会进入 `waiting_confirmation`，需人工确认后继续

## What Changed Recently / 最近更新

最近与本模块相关的关键变化：

- 新增按 `source_module` / `metadata_filters` 查询统一任务
- 新增 `update_task_metadata()`，支持持续写入阶段元数据
- 新增 `WorkflowTaskBridge.list_reflection_tasks()` / `list_upgrade_tasks()`
- `reflection` 和 `upgrade` 已自动同步到统一任务管理
- workflow bridge 会把 upgrade 阶段状态同步到任务 metadata 与 supervision record
- Mission 子任务分配新增 task_scope 约束（internal/external 注册表隔离）
- `required_resources` 显式执行方引用新增存在性校验（不存在即 `resource_gap`）
- 分配成功后自动写入 `worker_dispatch_enabled=true`，进入待执行派发链路
- 增加分配范围与执行方校验回归测试

## Limitations / 当前限制

- `reflection` 和 `upgrade` 目前是“同步进统一任务管理”，不是把全部内部子步骤完全重建成任务树
- 更细粒度的 upgrade 子阶段监督目前仍以 `workflow_status` + supervision note 为主
- 仓库内仍有部分历史文档和旧接口名未完全清理，阅读时以本 README 和源码为准
- 外部执行方健康状态是运行时变量，可能因网络或服务抖动导致任务临时进入 `resource_gap/suspended`