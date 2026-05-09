"""
Background Tasks Module - 后台任务模块

提供统一的后台任务管理、监控和调度能力。
此模块独立于具体业务逻辑，可被反思、学习等系统复用。

主要组件：
- monitor: 任务监控器
- queue: 优先级任务队列
"""

from zentex.background_tasks.monitor import (
    BackgroundTaskMonitor,
    TaskStatus,
    TaskType,
    TaskRecord,
    MetricsSnapshot,
    HealthStatus,
    get_monitor,
    reset_monitor,
)

from zentex.background_tasks.queue import (
    PriorityTaskQueue,
    TaskPriority,
    PriorityTask,
    get_task_queue,
    reset_task_queue,
)

__all__ = [
    # Monitor
    "BackgroundTaskMonitor",
    "TaskStatus",
    "TaskType",
    "TaskRecord",
    "MetricsSnapshot",
    "HealthStatus",
    "get_monitor",
    "reset_monitor",
    # Queue
    "PriorityTaskQueue",
    "TaskPriority",
    "PriorityTask",
    "get_task_queue",
    "reset_task_queue",
]
