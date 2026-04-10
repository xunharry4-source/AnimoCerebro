# Task Management Module

任务管理模块，采用模块化设计，遵循单一职责原则。

## 文件结构

```
tasks/
├── index.ts                      # 模块导出入口
├── types.ts                      # TypeScript 类型定义
├── ZentexTaskManager.tsx         # 主组件（列表页）
├── TaskDetailPage.tsx            # 任务详情页组件
├── TaskStatusChip.tsx            # 状态徽章组件
├── TaskTabPanel.tsx              # 标签面板组件
├── useTaskManagement.ts          # 任务管理自定义 Hook
└── README.md                     # 本文档
```

## 组件说明

### ZentexTaskManager
主组件，负责任务列表的展示和标签页导航。
- 5个标签页：进行中、待处理、待确认、已完成、已取消
- 实时数据更新（WebSocket）
- 点击任务可跳转到详情页

### TaskDetailPage
任务详情页组件，显示单个任务的完整信息。
- 任务基本信息（ID、标题、类型、优先级、状态等）
- 子任务列表和统计
- 依赖关系（前置和后置）
- 备注信息
- 支持从子任务跳转到父任务或其他相关任务

### TaskStatusChip
显示任务状态的彩色徽章组件。

### TaskTabPanel
Material-UI TabPanel 的封装，用于标签页内容切换。

### useTaskManagement
自定义 Hook，封装所有任务管理逻辑：
- 数据获取（按状态分类）
- WebSocket 连接和实时更新
- 标签页状态管理
- 错误处理

### types.ts
TypeScript 类型定义：
- `TaskStatus` - 任务状态枚举
- `ZentexTask` - 任务接口
- `TasksByStatus` - 按状态分类的任务集合
- `TabPanelProps` - 标签面板属性

## 使用示例

```tsx
import { ZentexTaskManager, TaskDetailPage } from './pages/tasks';

// 在路由中使用
<Route path="/console/tasks" element={<ZentexTaskManager />} />
<Route path="/console/tasks/:task_id" element={<TaskDetailPage />} />
```

## API 端点

### 列表页
- `GET /api/web/tasks/by-status` - 获取按状态分类的任务
- `WS /api/web/tasks/stream` - WebSocket 实时更新

### 详情页
- `GET /api/web/tasks/{task_id}/detail` - 获取任务详细信息
- `GET /api/web/tasks/{task_id}/subtasks` - 获取子任务列表
- `POST /api/web/tasks/{task_id}/decompose` - 触发任务分解
- `GET /api/web/tasks/{task_id}/execution-history` - 获取执行历史

## 未来扩展

计划添加的组件：
- `TaskTable.tsx` - 可复用的任务表格组件
- `InterventionDialog.tsx` - 人工干预对话框
- `TaskFilters.tsx` - 任务筛选组件
- `DependencyGraph.tsx` - 依赖关系可视化组件
- `ExecutionTimeline.tsx` - 执行时间线组件
