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

## What Changed Recently / 最近更新

最近与本模块相关的关键变化：

- 新增按 `source_module` / `metadata_filters` 查询统一任务
- 新增 `update_task_metadata()`，支持持续写入阶段元数据
- 新增 `WorkflowTaskBridge.list_reflection_tasks()` / `list_upgrade_tasks()`
- `reflection` 和 `upgrade` 已自动同步到统一任务管理
- workflow bridge 会把 upgrade 阶段状态同步到任务 metadata 与 supervision record

## Limitations / 当前限制

- `reflection` 和 `upgrade` 目前是“同步进统一任务管理”，不是把全部内部子步骤完全重建成任务树
- 更细粒度的 upgrade 子阶段监督目前仍以 `workflow_status` + supervision note 为主
- 仓库内仍有部分历史文档和旧接口名未完全清理，阅读时以本 README 和源码为准
