# TaskExecutionWorker — 任务执行层

## 职责

`zentex.tasks.execution` 是任务-插件闭环的**核心驱动层**。

它解决的核心问题：路由层（`UnifiedTaskRouter`）已选好执行插件，但之前没有任何代码负责**真正调用插件**并把结果写回任务记录。本模块填补这个缺口。

```
Before:  Task(TODO) → Router 选好插件 → ❌ 死路
After:   Task(TODO) → Router 选好插件 → Worker 执行 → Task(DONE + execution_output)
```

---

## 模块结构

```
tasks/execution/
├── __init__.py          # 导出 TaskExecutionWorker, WorkerConfig, WorkerCycleStats
└── worker.py            # 核心实现
```

---

## 核心类

### `TaskExecutionWorker`

调度→执行→回写的主体。每次 `run_cycle()` 完成一轮：

1. 从 DB 拉取一批 `status='todo'` 的任务
2. 过滤：所有 `depends_on` 任务都是 `done` + `attempt_count < max_attempts`
3. 标记 `IN_PROGRESS`，`attempt_count += 1`
4. 通过 `router.get_dispatch_decision()` 选插件，失败则直接匹配
5. 带超时地调用 `executor.execute_on_plugin()`
6. 根据结果更新 DB：

   | 结果 | status | 其他字段 |
   |------|--------|---------|
   | 成功 | `done` | `execution_output`, `dispatch_plugin_id`, `execution_finished_at` |
   | 失败 + 可重试 | `todo` | `last_error`（回队列） |
   | 失败 + 耗尽次数 | `failed` | `last_error`, `execution_finished_at` |
   | 无插件匹配 | `todo` | `last_error`（跳过本轮） |

7. 调用 `router.record_execution_result()` 更新插件信用分

### `WorkerConfig`

```python
@dataclass
class WorkerConfig:
    batch_size: int = 20                    # 每轮最多处理的任务数
    execution_timeout_seconds: float = 300.0 # 单次插件调用的超时秒数
    max_attempts: int = 3                   # 永久失败前的最大尝试次数
    enable_fallback: bool = True            # 是否在路由失败时直接匹配插件
    allowed_task_types: Optional[List[str]] = None  # None = 全部类型
```

### `WorkerCycleStats`

每轮 `run_cycle()` 返回，用于日志与监控：

```python
@dataclass
class WorkerCycleStats:
    cycle_started_at: str       # ISO 时间戳
    tasks_dispatched: int       # 本轮尝试处理总数
    tasks_succeeded: int        # 成功完成
    tasks_failed: int           # 永久失败
    tasks_skipped: int          # 无插件，跳过
    tasks_retried: int          # 暂时失败，重入队
    errors: List[Dict]          # Worker 级不可恢复错误
    cycle_duration_ms: int      # 本轮耗时毫秒
```

---

## 使用方法

### 基础接入

```python
from zentex.tasks.execution.worker import TaskExecutionWorker, WorkerConfig
from zentex.tasks.scheduling.loop_scheduler import TaskAutoLoopScheduler

# 1. 构建 Worker
worker = TaskExecutionWorker(
    task_dao=task_dao,                      # TaskDAO 实例
    router=unified_task_router,             # UnifiedTaskRouter（可为 None）
    internal_executor=internal_executor,    # InternalPluginExecutor（可为 None）
    config=WorkerConfig(
        batch_size=20,
        max_attempts=3,
        execution_timeout_seconds=300.0,
    ),
)

# 2. 注入调度器（推荐方式）
scheduler = TaskAutoLoopScheduler(
    task_service=task_service,
    interval_seconds=15,
    execution_worker=worker,
)
scheduler.start()
```

### 热插拔（插件层延迟初始化时）

```python
# 应用启动时先启动调度器（无 Worker）
scheduler = TaskAutoLoopScheduler(task_service=task_service)
scheduler.start()

# 插件层注册完成后再挂上 Worker
scheduler.set_execution_worker(worker)
```

### 手动触发一轮（测试 / 调试）

```python
import asyncio
stats = asyncio.run(worker.run_cycle())
print(f"dispatched={stats.tasks_dispatched} ok={stats.tasks_succeeded}")
```

---

## 依赖关系

```
TaskExecutionWorker
    ├── TaskDAO              (zentex.tasks.persistence.dao)
    ├── UnifiedTaskRouter    (zentex.tasks.dispatch.router_impl)  ← 可选
    ├── InternalPluginExecutor (zentex.tasks.dispatch.internal)   ← 可选
    ├── SubtaskIntent        (zentex.tasks.models)
    └── DispatchResult       (zentex.tasks.dispatch.models)
```

两个可选依赖均可为 `None`：
- `router=None` → Worker 直接调用 `executor.get_matching_plugins_for_subtask()` 匹配
- `internal_executor=None` → 无插件可调用，所有任务标记为 `skipped`

---

## 执行结果字段（DB 层）

Worker 写回的字段均由 `migrate_task_schema()` 自动在 `tasks` 表中创建：

| 列名 | 类型 | 含义 |
|------|------|------|
| `execution_output` | TEXT (JSON) | 插件返回的结构化输出 |
| `dispatch_plugin_id` | TEXT | 实际执行的插件 ID |
| `execution_started_at` | TIMESTAMP | 执行开始时间（标记 IN_PROGRESS 时写入） |
| `execution_finished_at` | TIMESTAMP | 执行结束时间（成功/失败均写入） |
| `last_error` | TEXT | 最近一次错误信息（每次尝试覆盖） |
| `attempt_count` | INTEGER | 已尝试次数（每次进入 IN_PROGRESS 时 +1） |

---

## 错误处理策略

| 错误类型 | 处理方式 |
|----------|----------|
| 插件执行异常 | 捕获，写 `last_error`，根据 `attempt_count` 决定重试还是失败 |
| 执行超时 | `asyncio.wait_for` 捕获 `TimeoutError`，同上处理 |
| 路由异常 | 降级到直接匹配，不中断本任务处理 |
| DB 写入异常 | 记录 error log，纳入 `WorkerCycleStats.errors` |
| Worker 级未捕获异常 | 记录 error log，任务标记 `failed`，Worker 继续处理下一个任务 |

**原则：单个任务失败不影响同批次其他任务的处理。**

---

## 与其他层的边界

| 层 | 职责 | 不做什么 |
|----|------|---------|
| `TaskExecutionWorker` | 调度循环、执行、结果回写 | 不直接管理插件生命周期 |
| `UnifiedTaskRouter` | 路由决策、信用评分 | 不执行插件 |
| `InternalPluginExecutor` | 插件调用、超时处理 | 不管任务状态 |
| `TaskDAO` | DB 读写 | 不管业务逻辑 |
| `TaskManagementService` | 状态机、验证、API | 不轮询执行 |
