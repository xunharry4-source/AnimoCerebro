# Supervision Module / 监督模块

## Overview / 概述

`zentex.supervision` 为系统提供运行监督能力，主要负责：

- 执行记录
- 规则校验
- 警报
- 人工干预
- 任务级监督集成

当前核心文件：

- [ai_supervisor.py](src/zentex/supervision/ai_supervisor.py)
- [integration.py](src/zentex/supervision/integration.py)
- [service.py](src/zentex/supervision/service.py)

## Current Component Roles / 当前组件职责

### 1. AISupervisor

[ai_supervisor.py](src/zentex/supervision/ai_supervisor.py) 中的 `AISupervisor` 是底层监督引擎。

负责：

- 保存 `ExecutionRecord`
- 执行监督规则
- 生成 `SupervisionAlert`
- 维护全局监督级别

### 2. TaskSupervisor

`TaskSupervisor` 是任务级监督适配层，负责：

- 按 `task_id` 建立 supervision record 映射
- 标记运行中 / 完成 / 失败
- 提供任务监督状态查询

### 3. SupervisedTaskManager

[integration.py](src/zentex/supervision/integration.py) 中的 `SupervisedTaskManager` 负责把监督能力接到 `TaskManagementService` 上。

主要作用：

- 创建任务时自动建立 supervision record
- 在监督下执行任务
- 暴露人工干预入口

### 4. SupervisionService

[service.py](src/zentex/supervision/service.py) 是对外统一服务接口，供 Web console 或其他模块使用。

## Current Relationship with Tasks / 与任务模块的关系

监督模块本身不负责创建业务任务，它依附于任务模块工作。

当前关系是：

1. `TaskManagementService` 负责任务状态机
2. `SupervisedTaskManager` 在任务侧增加监督记录
3. `WorkflowTaskBridge` 把 `reflection` / `upgrade` 同步成统一任务
4. bridge 再把关键阶段写入 supervision record

也就是说，现在 `supervision` 已经参与：

- 统一任务创建后的基础监督
- `upgrade` 阶段信息备注
- 统一任务人工干预入口

## Built-in Rules / 内置规则

当前默认规则包括：

- destructive operations 检查
- resource limit 检查
- data access compliance 检查
- action frequency 检查

这些规则目前更偏“基础框架层”，还不是按业务域深度定制。

## What Changed Recently / 最近更新

与最近改动相关的关键点：

- `reflection` 和 `upgrade` 现在都会同步成统一任务
- 这些统一任务在创建时会自动建立 supervision record
- `upgrade` 的阶段状态会继续写入 supervision record 的：
  - `parameters`
  - `supervisor_notes`

这意味着 supervision 不再只是一个独立仪表盘，而是开始承接真实工作流状态。

## Current Boundaries / 当前边界

需要明确几点：

- `reflection` 仍然保留自己的内部队列和 monitor
- `upgrade` 仍然保留自己的管理账本和执行监控
- `supervision` 现在提供的是统一任务上的“基础监督层”

换句话说：

- 已经接入统一监督
- 但还没有把所有内部子阶段完全交给 supervision engine 单独裁决

## Recommended Use / 推荐使用方式

如果一个模块要接入监督，推荐顺序是：

1. 先接入 `zentex.tasks`
2. 再通过 `SupervisedTaskManager` 建立监督记录
3. 如有阶段推进，再持续更新任务 metadata 与 supervision note

不要直接在业务模块中各自重复造一套监督状态机。
