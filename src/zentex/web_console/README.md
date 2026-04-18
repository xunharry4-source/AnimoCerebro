# Web Console Module / Web 控制台模块

## Overview / 概述

`zentex.web_console` 是系统对外的 Web/API 展示层，负责把后端运行态、安全地暴露成控制台页面和接口。

当前与本轮改动最相关的能力有两类：

- `/console/tasks` 对统一任务系统的展示
- `/console/upgrades` 对升级管理账本的展示

关键后端入口：

- [routers/tasks.py](/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/web_console/routers/tasks.py)
- [routers/upgrades.py](/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/web_console/routers/upgrades.py)
- [services/upgrades.py](/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/web_console/services/upgrades.py)
- [contracts/upgrades.py](/Users/harry/Documents/git/AnimoCerebro-V2/src/zentex/web_console/contracts/upgrades.py)

## Tasks Console / 任务控制台

### Current Data Source / 当前数据源

`/console/tasks` 的后端来源是 `TaskManagementService`，不是前端自己拼装。

当前主要接口：

- `GET /api/web/tasks`
- `GET /api/web/tasks/by-status`
- `GET /api/web/tasks/{task_id}/detail`
- `GET /api/web/tasks/{task_id}/subtasks`
- `GET /api/web/tasks/{task_id}/execution-history`
- `WS /api/web/tasks/stream`

### Current Semantics / 当前语义

统一任务现在不仅包含“原生任务”，还包含通过 workflow bridge 同步进来的：

- `reflection` 工作流任务
- `upgrade` 工作流任务

这些任务的来源信息写在 task metadata 中，例如：

- `source_module`
- `workflow_kind`
- `workflow_status`
- `workflow_progress`

因此 `/console/tasks` 现在本质上已经是跨模块统一任务视图。

## Upgrades Console / 升级控制台

### Current Data Source / 当前数据源

`/console/upgrades` 的后端来源是升级管理存储和升级账本，不是页面直接扫文件。

当前主要接口：

- `GET /api/web/upgrades/overview`
- `GET /api/web/upgrades/by-lifecycle-view`
- `GET /api/web/upgrades/{record_id}`
- `GET /api/web/upgrades/{record_id}/audit-events`
- `GET /api/web/upgrades/{record_id}/memory-records`
- `POST /api/web/upgrades/llm/execute`
- `POST /api/web/upgrades/plugins/execute`
- `POST /api/web/upgrades/{record_id}/cancel`
- `POST /api/web/upgrades/{record_id}/cleanup-failed-candidate`

### Prompt Upgrade Fields / Prompt 升级字段

升级详情现在已经不只返回通用生命周期字段，还会带出 prompt 升级相关展示字段：

- `prompt_target_file`
- `prompt_upgrade_sections`
- `prompt_upgrade_notes`
- `prompt_upgrade_summary`

这些字段由后端服务层从 `record.payload` 里提炼出来，前端不需要再自己解析深层 payload。

## Fail-closed Contract / 故障关闭约束

控制台路由遵循 fail-closed：

- 核心服务缺失时返回 `503`
- 不允许因为依赖缺失而静默返回空数据
- WebSocket 缺少服务时会显式关闭，而不是挂死

这点在 `tasks.py` 和 `upgrades.py` 的 `_require_*` 依赖守卫里已经落地。

## Relationship with Runtime Modules / 与运行时模块的关系

控制台不拥有业务状态机，它只读取和调用：

- `zentex.tasks`
- `zentex.upgrade`
- `zentex.reflection`
- `zentex.supervision`

控制台的职责是：

- 提供稳定接口
- 展示统一视图
- 触发受控操作

而不是在页面层或 router 层重写业务逻辑。

## What Changed Recently / 最近更新

- 统一任务已经开始承载 `reflection / upgrade` 工作流任务
- upgrades API 已增加更适合 UI 的 prompt 升级字段
- upgrades 管理页的数据来源已和 SQLite 管理账本一致
- tasks 页实际承载的已不只是普通任务，而是统一工作流任务视图

## Limitations / 当前限制

- `/console/tasks` 当前后端接口还没有单独暴露 `source_module` 过滤参数；服务层已经支持，控制台接口层后续可以继续补
- `/console/upgrades` 已具备 prompt 升级展示数据，但页面是否完整渲染取决于前端实现状态
