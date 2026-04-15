"""
Background Task Monitor - 后台任务监控系统

负责统一跟踪所有后台任务状态、收集执行指标、提供健康检查接口。
此模块独立于具体的业务逻辑（反思/学习），仅提供通用的任务监控能力。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskType(str, Enum):
    """任务类型枚举"""
    REFLECTION = "reflection"
    LEARNING = "learning"


@dataclass
class TaskRecord:
    """任务记录"""
    task_id: str
    task_type: TaskType
    subtype: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 2  # 0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    progress: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    worker_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "subtype": self.subtype,
            "status": self.status.value,
            "priority": self.priority,
            "progress": self.progress,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }


@dataclass
class MetricsSnapshot:
    """指标快照"""
    timestamp: datetime
    total_tasks: int = 0
    tasks_by_status: Dict[str, int] = field(default_factory=dict)
    tasks_by_type: Dict[str, int] = field(default_factory=dict)
    avg_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    queue_length: int = 0
    thread_pool_utilization: float = 0.0
    process_pool_utilization: float = 0.0


@dataclass
class HealthStatus:
    """健康状态"""
    is_healthy: bool = True
    checks: Dict[str, bool] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BackgroundTaskMonitor:
    """
    后台任务监控器
    
    线程安全，支持并发访问。
    不依赖任何具体业务模块，仅提供通用监控能力。
    """

    def __init__(self, *, metrics_retention_hours: int = 24):
        self._tasks: Dict[str, TaskRecord] = {}
        self._metrics_history: List[MetricsSnapshot] = []
        self._lock = threading.RLock()
        self._metrics_retention_hours = metrics_retention_hours
        self._alert_callbacks: List[callable] = []
        
        logger.info("BackgroundTaskMonitor initialized")

    def register_task(self, task_id: str, task_type: TaskType, **kwargs) -> None:
        """
        注册新任务
        
        Args:
            task_id: 任务ID
            task_type: 任务类型
            **kwargs: 其他任务属性
        """
        with self._lock:
            if task_id in self._tasks:
                logger.warning(f"Task {task_id} already registered, updating")
            
            task = TaskRecord(
                task_id=task_id,
                task_type=task_type,
                **{k: v for k, v in kwargs.items() if hasattr(TaskRecord, k)}
            )
            self._tasks[task_id] = task
            logger.debug(f"Task registered: {task_id} ({task_type.value})")

    def update_status(self, task_id: str, status: TaskStatus, **kwargs) -> None:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            **kwargs: 其他更新字段
        """
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Task {task_id} not found")
                return
            
            task = self._tasks[task_id]
            old_status = task.status
            task.status = status
            
            # 自动设置时间戳
            if status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = datetime.now(timezone.utc)
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = datetime.now(timezone.utc)
                if task.started_at:
                    task.duration_ms = int(
                        (task.completed_at - task.started_at).total_seconds() * 1000
                    )
            
            # 更新其他字段
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            
            logger.debug(f"Task {task_id} status: {old_status.value} -> {status.value}")
            
            # 触发告警检查
            if status == TaskStatus.FAILED:
                self._check_failure_alerts(task)

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """获取任务记录"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(
        self,
        *,
        task_type: Optional[TaskType] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TaskRecord]:
        """
        列出任务
        
        Args:
            task_type: 过滤任务类型
            status: 过滤状态
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            任务列表
        """
        with self._lock:
            tasks = list(self._tasks.values())
            
            if task_type:
                tasks = [t for t in tasks if t.task_type == task_type]
            if status:
                tasks = [t for t in tasks if t.status == status]
            
            # 按创建时间倒序排序
            tasks.sort(key=lambda t: t.created_at, reverse=True)
            
            return tasks[offset:offset + limit]

    def get_metrics(self) -> MetricsSnapshot:
        """
        获取当前指标快照
        
        Returns:
            指标快照
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            tasks = list(self._tasks.values())
            
            # 统计状态分布
            status_counts = defaultdict(int)
            type_counts = defaultdict(int)
            durations = []
            
            for task in tasks:
                status_counts[task.status.value] += 1
                type_counts[task.task_type.value] += 1
                if task.duration_ms is not None:
                    durations.append(task.duration_ms)
            
            # 计算持续时间统计
            avg_duration = sum(durations) / len(durations) if durations else 0
            sorted_durations = sorted(durations)
            p95_idx = int(len(sorted_durations) * 0.95)
            p99_idx = int(len(sorted_durations) * 0.99)
            p95_duration = sorted_durations[p95_idx] if sorted_durations else 0
            p99_duration = sorted_durations[p99_idx] if sorted_durations else 0
            
            # 计算成功率
            completed = status_counts.get("COMPLETED", 0)
            failed = status_counts.get("FAILED", 0)
            total_finished = completed + failed
            success_rate = completed / total_finished if total_finished > 0 else 0
            failure_rate = failed / total_finished if total_finished > 0 else 0
            
            # Pending任务数作为队列长度
            queue_length = status_counts.get("PENDING", 0)
            
            snapshot = MetricsSnapshot(
                timestamp=now,
                total_tasks=len(tasks),
                tasks_by_status=dict(status_counts),
                tasks_by_type=dict(type_counts),
                avg_duration_ms=avg_duration,
                p95_duration_ms=p95_duration,
                p99_duration_ms=p99_duration,
                success_rate=success_rate,
                failure_rate=failure_rate,
                queue_length=queue_length,
            )
            
            # 保存历史（定期清理）
            self._metrics_history.append(snapshot)
            self._cleanup_old_metrics(now)
            
            return snapshot

    def get_health(self) -> HealthStatus:
        """
        获取健康状态
        
        Returns:
            健康状态
        """
        with self._lock:
            health = HealthStatus()
            
            # 检查1: 任务失败率
            metrics = self.get_metrics()
            if metrics.failure_rate > 0.3:  # 失败率超过30%
                health.is_healthy = False
                health.checks["failure_rate"] = False
                health.issues.append(
                    f"High failure rate: {metrics.failure_rate:.1%}"
                )
            else:
                health.checks["failure_rate"] = True
            
            # 检查2: 队列积压
            if metrics.queue_length > 100:
                health.is_healthy = False
                health.checks["queue_length"] = False
                health.issues.append(
                    f"Queue backlog: {metrics.queue_length} tasks pending"
                )
            else:
                health.checks["queue_length"] = True
            
            # 检查3: 系统可访问性
            health.checks["accessible"] = True
            
            return health

    def add_alert_callback(self, callback: callable) -> None:
        """
        添加告警回调
        
        Args:
            callback: 告警回调函数，接收 (task: TaskRecord) 参数
        """
        self._alert_callbacks.append(callback)

    def _check_failure_alerts(self, task: TaskRecord) -> None:
        """检查是否需要触发失败告警"""
        for callback in self._alert_callbacks:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def _cleanup_old_metrics(self, now: datetime) -> None:
        """清理过期的指标历史"""
        cutoff = now.timestamp() - (self._metrics_retention_hours * 3600)
        self._metrics_history = [
            m for m in self._metrics_history
            if m.timestamp.timestamp() > cutoff
        ]

    def clear_completed_tasks(self, older_than_hours: int = 24) -> int:
        """
        清理已完成的任务记录
        
        Args:
            older_than_hours: 清理多少小时前的任务
        
        Returns:
            清理的任务数量
        """
        with self._lock:
            cutoff = datetime.now(timezone.utc).timestamp() - (older_than_hours * 3600)
            to_remove = [
                task_id for task_id, task in self._tasks.items()
                if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED)
                and task.completed_at
                and task.completed_at.timestamp() < cutoff
            ]
            
            for task_id in to_remove:
                del self._tasks[task_id]
            
            logger.info(f"Cleared {len(to_remove)} old task records")
            return len(to_remove)


# 全局单例
_monitor_instance: Optional[BackgroundTaskMonitor] = None
_monitor_lock = threading.Lock()


def get_monitor() -> BackgroundTaskMonitor:
    """获取全局监控器实例"""
    global _monitor_instance
    if _monitor_instance is None:
        with _monitor_lock:
            if _monitor_instance is None:
                _monitor_instance = BackgroundTaskMonitor()
    return _monitor_instance


def reset_monitor() -> None:
    """重置监控器（主要用于测试）"""
    global _monitor_instance
    with _monitor_lock:
        _monitor_instance = None
