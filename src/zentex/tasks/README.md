# Tasks Module / 任务模块

## Overview / 概述

`zentex.tasks` 是系统的统一任务管理层，负责：

- 任务创建、状态流转、依赖管理
- Mission 拆解与分发
- **任务到插件的调度执行与结果回写（闭环）**
- 统一任务查询与持久化
- 对 `reflection`、`upgrade` 等外部工作流提供统一托管入口

---

## Architecture / 架构总览

```
外部调用方
    │
    ▼
TaskManagementService          ← 状态机 + 持久化边界
    │
    ├── decompose_and_dispatch_mission()   ← Mission 拆解为子任务
    │
    └── complete_task_with_verification()  ← 完成时持久化执行结果
              │
              └── _persist_execution_result()   ← 写 execution_output 到 DB


后台调度器 (每 15 秒)
    │
    ▼
TaskAutoLoopScheduler._run_cycle()
    │
    ├── Pass 1: TaskExecutionWorker.run_cycle()     ← ★ 核心执行闭环
    │       │
    │       ├── 查 TODO 任务 + 检查 depends_on 全部 DONE
    │       ├── UnifiedTaskRouter.get_dispatch_decision()  ← 选插件
    │       ├── InternalPluginExecutor.execute_on_plugin() ← 真实执行
    │       ├── 写 execution_output / dispatch_plugin_id / status
    │       └── router.record_execution_result()    ← 更新插件信用分
    │
    ├── Pass 2: check_auto_resume_tasks()           ← 自动恢复挂起任务
    └── Pass 3: check_timeout_and_republish_tasks() ← 超时任务重入队列
```

---

## 核心文件 / Key Files

| 文件 | 职责 |
|------|------|
| `service.py` | `TaskManagementService` — 状态机、持久化、验证 |
| `execution/worker.py` | `TaskExecutionWorker` — 调度→执行→结果回写 |
| `scheduling/loop_scheduler.py` | `TaskAutoLoopScheduler` — 后台周期驱动 |
| `dispatch/router_impl.py` | `UnifiedTaskRouter` — 插件路由决策 |
| `dispatch/internal.py` | `InternalPluginExecutor` — 内部插件调用 |
| `persistence/dao.py` | `TaskDAO` — SQLite 数据访问 |
| `schema.py` | Schema 建表 + **自动列迁移** |
| `models/models.py` | `ZentexTask`, `SubtaskIntent`, `TaskContract` |
| `core/llm_prompt.py` | 任务拆解 LLM Prompt 构造（分段化） |
| `verification/llm_prompt.py` | 验证评估 LLM Prompt 构造（分段化） |

---

## Data Model — ZentexTask 字段

### 基础字段（原有）

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `str` | 主键 |
| `status` | `TaskStatus` | 状态机枚举 |
| `priority` | `TaskPriority` | critical / high / medium / low |
| `task_type` | `TaskType` | cognitive_step / agent_delegation / system_action / intervention / mission |
| `depends_on` | `List[str]` | 前置任务 ID 列表 |
| `contract` | `TaskContract` | 含重试预算、验证配置等 |
| `metadata` | `Dict` | 工作流元数据（不影响状态机） |

### 执行结果字段（新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| `execution_output` | `Optional[Dict]` | 插件返回的结构化输出（JSON） |
| `dispatch_plugin_id` | `Optional[str]` | 实际执行该任务的插件 ID |
| `execution_started_at` | `Optional[datetime]` | 执行开始时间 |
| `execution_finished_at` | `Optional[datetime]` | 执行结束时间 |
| `last_error` | `Optional[str]` | 最近一次失败的错误信息 |
| `attempt_count` | `int` | 已尝试执行次数（默认 0） |

---

## Task Status Machine / 状态流转

```
TODO ──────────────────────────────────┐
  │                                    │
  ▼ (Worker 调度)                      │
IN_PROGRESS ──► WAITING_CONFIRMATION   │ (验证后重试)
  │               │                   │
  │               ▼                   │
  │             DONE ──► ARCHIVED     │
  │               │                   │
  ▼               ▼                   │
FAILED ──────────────────────────────►┘  (retry: 回 TODO)
  │
SUSPENDED ──► TODO / IN_PROGRESS / FAILED / ARCHIVED
  │
BLOCKED ──► TODO / IN_PROGRESS / FAILED / SUSPENDED / ARCHIVED
```

状态流转由 `TaskManagementService.update_task_status()` 强校验，非法跳转抛 `TaskStateError`。

---

## Execution Worker / 执行 Worker

### 启动方式

```python
from zentex.tasks.execution.worker import TaskExecutionWorker, WorkerConfig
from zentex.tasks.scheduling.loop_scheduler import TaskAutoLoopScheduler

worker = TaskExecutionWorker(
    task_dao=task_dao,
    router=unified_task_router,
    internal_executor=internal_plugin_executor,
    config=WorkerConfig(
        batch_size=20,          # 每轮最多处理 20 个任务
        max_attempts=3,         # 最多重试 3 次
        execution_timeout_seconds=300.0,  # 单次执行超时 5 分钟
    ),
)

scheduler = TaskAutoLoopScheduler(
    task_service=task_service,
    interval_seconds=15,
    execution_worker=worker,    # 注入 Worker
)
scheduler.start()
```

### 运行时热插拔

```python
# 插件层启动完成后再注入 Worker（避免启动顺序死锁）
scheduler.set_execution_worker(worker)
```

### Worker 处理流程

```
1. 查询 status='todo' 的任务（批量）
2. 过滤：depends_on 全部 DONE + attempt_count < max_attempts
3. 标记 IN_PROGRESS，attempt_count += 1
4. router.get_dispatch_decision(subtask_intent) → 选择最优插件
5. executor.execute_on_plugin(plugin_id, subtask, task_id)
6a. 成功 → status=done, execution_output=结果JSON, dispatch_plugin_id=插件ID
6b. 失败 & 未耗尽次数 → status=todo（回队列重试），last_error=错误信息
6c. 失败 & 耗尽次数 → status=failed, last_error=最终错误
7. router.record_execution_result() → 更新插件信用分
```

### WorkerCycleStats（每轮返回）

```python
@dataclass
class WorkerCycleStats:
    tasks_dispatched: int     # 本轮尝试处理的任务数
    tasks_succeeded: int      # 成功完成数
    tasks_failed: int         # 永久失败数
    tasks_skipped: int        # 无插件匹配，跳过数
    tasks_retried: int        # 暂时失败，重入队列数
    errors: List[Dict]        # 不可恢复的 Worker 级错误
    cycle_duration_ms: int    # 本轮耗时（毫秒）
```

---

## Schema Migration / 数据库自动迁移

`tasks/schema.py` 提供幂等安全的自动迁移，每次 `TaskDAO` 初始化时自动调用：

```python
from zentex.tasks.schema import migrate_task_schema
migrate_task_schema(db)  # 只添加缺失列，不删除或修改现有数据
```

**当前 tasks 表结构（v2 + 执行字段）：**

```
task_id, parent_task_id, subtask_ids, depends_on, bundle_id, subtask_id,
idempotency_key, title, task_type, status, priority, progress,
originator_id, target_id, remarks, started_at, completed_at,
deadline, estimated_duration, tags, contract, metadata,
last_updated_at, created_at,
── 新增 ──
execution_output, dispatch_plugin_id, execution_started_at,
execution_finished_at, last_error, attempt_count
```

---

## LLM Prompt Structure / LLM 提问结构

任务模块内的所有 LLM 提问已拆出为独立文件，禁止在业务文件中内联 prompt 字符串。

| 文件 | 用途 |
|------|------|
| `core/llm_prompt.py` | 任务拆解（`DecompositionPromptSegments`，6 段，60/40 截断） |
| `verification/llm_prompt.py` | LLM 评估验证（5 段结构化输出） |

每个 prompt 文件遵循分离合同：

| 文件 | 职责 | 禁止 |
|------|------|------|
| `llm_prompt.py` | 构造分段 prompt，预处理输入 | 调用 LLM，写数据库 |
| 调用方（decomposer / verifier） | 调用 LLM，处理结果 | 内联 prompt 字符串 |

---

## Integration Contract / 集成边界

其他模块接入任务系统时，必须遵守：

- **不直接写任务内部共享状态**
- **不直接操作 DAO 或数据库表**
- **统一通过** `TaskManagementService` / `TaskServiceInterface`
- 工作流同步统一经由 `WorkflowTaskBridge`
- 读取执行结果通过 `task.execution_output` 字段（DB 层持久化）

---

## What Changed Recently / 最近更新

| 变更 | 文件 |
|------|------|
| ★ 新建执行闭环：`TaskExecutionWorker` | `execution/worker.py` |
| ★ 调度器集成执行 Worker（Pass 1） | `scheduling/loop_scheduler.py` |
| ★ Schema 自动迁移：`migrate_task_schema()` | `schema.py` |
| ★ 6 个新执行结果字段 | `models/models.py` + `tasks` 表 |
| ★ `complete_task_with_verification()` 持久化结果 | `service.py` |
| LLM prompt 拆分为独立文件（分段化） | `core/llm_prompt.py`, `verification/llm_prompt.py` |
| 按 `source_module` / `metadata_filters` 查询 | `service.py` |
| `WorkflowTaskBridge` 接入 reflection / upgrade | `integration/workflow_bridge.py` |

---

## Limitations / 当前限制

- `InternalPluginExecutor` 的 `plugin_layer` 需在应用启动后通过 `scheduler.set_execution_worker()` 注入，首次调度周期前插件层必须已完成注册
- 当前 Worker 基于轮询（每 15 秒），高并发场景可考虑改为事件驱动（任务创建时主动触发一次 cycle）
- `reflection` / `upgrade` 的内部子步骤目前以 `workflow_status` + supervision note 为主，尚未完全重建为子任务树
