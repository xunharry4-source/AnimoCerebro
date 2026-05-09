# Tasks Console Page

## 页面定位

`/console/tasks` 现在展示的是统一任务视图，不只是“原生任务列表”。

当前页面展示的数据来源于 `zentex.tasks`，而 `zentex.tasks` 已开始承载：

- 普通任务
- `reflection` 同步进来的工作流任务
- `upgrade` 同步进来的工作流任务

## 当前前端结构

```
tasks/
├── index.ts
├── types.ts
├── ZentexTaskManager.tsx
├── TaskDetailPage.tsx
├── TaskStatusChip.tsx
├── TaskTabPanel.tsx
├── useTaskManagement.ts
└── README.md
```

## 当前页面能力

### ZentexTaskManager

主列表页，当前职责：

- 按状态展示任务
- 通过 WebSocket 接收实时更新
- 跳转到详情页

当前“任务”语义要理解为统一任务，不再局限于用户显式创建的任务。

### TaskDetailPage

详情页负责展示：

- 基础任务字段
- 子任务
- 依赖关系
- 备注
- 执行历史

如果任务来自 workflow bridge，额外重要的信息在 task metadata 中，例如：

- `source_module`
- `workflow_kind`
- `workflow_status`
- `workflow_progress`

## 当前后端接口

- `GET /api/web/tasks/by-status?limit_per_group=100&offset=0`
- `GET /api/web/tasks/{task_id}/detail`
- `GET /api/web/tasks/{task_id}/subtasks`
- `GET /api/web/tasks/{task_id}/execution-history`
- `WS /api/web/tasks/stream`

## 与后端的当前对应关系

### Reflection / Upgrade 统一任务

后端通过 `WorkflowTaskBridge` 把 `reflection` 和 `upgrade` 同步成统一任务，因此页面看到的任务可能不是用户手工创建的业务任务，而是工作流映射任务。

这类任务的判断依据不是 title，而是 metadata。

推荐前端后续优先使用：

- `metadata.source_module`
- `metadata.workflow_kind`
- `metadata.workflow_status`
- `metadata.workflow_progress`

而不是靠字符串猜测。

## 当前限制

- 当前页面文档不再假设 `/console/tasks` 只展示单一任务域
- 目前列表接口仍主要按状态分组，尚未单独提供按 `source_module` 的页面筛选体验
- 如果后续要把 `reflection` / `upgrade` 单独分栏展示，应直接基于 metadata 做前端筛选，或推动后端补显式过滤参数

## 推荐后续增强

- 增加 `source_module` 过滤器
- 在列表中展示 workflow 来源标记
- 在详情页增加 metadata 区块
- 对 `upgrade` 任务展示 `workflow_progress`
- 对 `reflection` 任务展示 `reflection_type`
