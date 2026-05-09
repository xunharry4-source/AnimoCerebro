# Upgrade Module / 升级模块

## Overview / 概述

`zentex.upgrade` 负责受控升级执行，包括：

- LLM 升级规划与执行
- 插件升级 / 新建插件执行
- 升级账本、审计、记忆
- prompt-only 升级
- section-aware prompt 优化执行

当前真实关键入口：

- [service.py](src/zentex/upgrade/service.py)
- [execution.py](src/zentex/upgrade/execution.py)
- [management.py](src/zentex/upgrade/management.py)
- [ledger.py](src/zentex/upgrade/ledger.py)

## Runtime Model / 当前运行模型

### 1. Planning / 规划

顶层门面是：

- `UpgradeFacade`

它负责：

- 判断是否升级
- 区分 LLM 升级与插件升级
- 生成 candidate
- 将执行委托给 `UpgradeExecutionService`

### 2. Execution / 执行

[execution.py](src/zentex/upgrade/execution.py) 是当前真实执行边界。

它负责：

- 创建和推进管理记录
- 调用 LLM / plugin runtime
- 写 audit / memory evidence
- 把关键状态同步到统一任务管理

### 3. Persistence / 持久化

升级模块现在已经统一落到 SQLite：

- 管理状态：`upgrade_management.sqlite3`
- 审计日志：`upgrade_audit.sqlite3`
- 升级记忆：`upgrade_memory.sqlite3`

其中：

- [management.py](src/zentex/upgrade/management.py) 负责管理状态
- [ledger.py](src/zentex/upgrade/ledger.py) 负责审计与记忆账本

`UpgradeManagementStore` 现在不是简单 JSON 文件，而是展开字段的 SQLite schema，并且查询和统计已直接走 SQL。

## Prompt Optimization / Prompt 升级能力

这是本轮升级模块最大的变化。

### 1. Prompt-only Upgrade / 纯 prompt 升级

`LLMUpgradeRequest` 现在支持 `upgrade_kind="prompt_optimization"`。  
这类升级不再允许走泛化 optimizer，而必须走受约束的 prompt optimizer。

### 2. Section-aware Prompt Execution / 分段感知 prompt 执行

核心文件：

- [llm/runtime.py](src/zentex/upgrade/llm/runtime.py)
- [llm/prompt_optimizer.py](src/zentex/upgrade/llm/prompt_optimizer.py)

当前执行约束：

- 只能修改候选中声明的 `prompt_file_path`
- 只能修改 `editable_prompt_sections`
- 不允许修改 immutable sections
- 必须返回 `prompt_guardrails`
- `preserved_intent` 必须为 `True`
- `forbidden_change_violations` 必须为空

### 3. Default Runtime / 默认执行链

`UpgradeExecutionService` 默认已经自动注入：

- `LLMSectionContentMutator`
- `build_section_aware_prompt_optimizer_runner(...)`

因此 prompt-only 升级现在是默认可执行路径，不需要外部再手工装配 runtime。

## Prompt Contracts / Prompt 升级合同

升级模块内的 prompt 已拆到独立 builder 文件，不再允许在业务执行器里内联大段 prompt。

当前关键文件：

- [llm/prompt_builders.py](src/zentex/upgrade/llm/prompt_builders.py)
- [skills/atomic_planner_llm_prompt.py](src/zentex/upgrade/skills/atomic_planner_llm_prompt.py)
- [skills/auto_debugger_llm_prompt.py](src/zentex/upgrade/skills/auto_debugger_llm_prompt.py)
- [skills/auto_reviewer_llm_prompt.py](src/zentex/upgrade/skills/auto_reviewer_llm_prompt.py)
- [ai_executors_llm_prompt.py](src/zentex/upgrade/ai_executors_llm_prompt.py)

这些 prompt 已 section 化，并由各自 `service.py` 提供升级合同：

- [llm/service.py](src/zentex/upgrade/llm/service.py)
- [skills/service.py](src/zentex/upgrade/skills/service.py)
- [service.py](src/zentex/upgrade/service.py)

## Workflow Integration / 统一任务集成

升级模块现在保留两层管理：

1. 自己的升级管理账本和执行监控
2. 同步进统一任务管理的工作流任务

同步桥接在：

- [tasks/integration/workflow_bridge.py](src/zentex/tasks/integration/workflow_bridge.py)

当前同步内容包括：

- `source_module="upgrade"`
- `workflow_status`
- `workflow_progress`
- `upgrade_action`
- `upgrade_target_kind`
- `candidate_version`

同时阶段信息还会写入 supervision record 的：

- `parameters`
- `supervisor_notes`

## Automated Skills / 自动化技能

升级模块仍保留自动化技能层：

- `AtomicUpgradePlanner`
- `AutomatedRootCauseAnalyzer`
- `AutomatedTwoStageReviewer`

它们负责：

- 将升级提案拆成原子任务
- 分析失败升级的根因
- 对候选结果做自动审查

但要注意：

- 它们是升级流程的辅助能力
- 当前最核心的生产执行边界仍是 `UpgradeExecutionService`

## What Changed Recently / 最近更新

- 升级管理状态从 JSON 统一迁移到 SQLite
- `UpgradeManagementStore` 已改为展开字段 schema + SQL 查询
- prompt-only 升级已成为正式执行路径
- section-aware prompt optimizer 已默认接入
- 升级记录 payload 已对前端提供更友好的 prompt 升级展示字段
- 升级生命周期现在会自动同步到统一任务管理和基础 supervision 记录

## Limitations / 当前限制

- 当前已支持“阶段级同步”，但还没有把 upgrade 的每个内部子步骤完全拆成统一任务树
- prompt 优化虽然已是正式执行路径，但最终效果仍取决于具体 LLM provider 和 mutator 输出质量
