"""
Async Reflection Service - 异步反思服务

提供异步的反思任务提交和管理接口。
此服务层包装原有的同步服务，不修改原有逻辑。
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from zentex.reflection.models import ReflectionType, ReflectionTrigger
from zentex.reflection.service import ReflectionService
from zentex.reflection.task_executor import ReflectionTaskExecutor
from zentex.background_tasks import (
    get_monitor,
    get_task_queue,
    TaskStatus,
    TaskType,
    TaskPriority,
)

logger = logging.getLogger(__name__)


class AsyncReflectionService:
    """
    异步反思服务
    
    职责：
    1. 接收反思请求，生成任务ID
    2. 将任务提交到优先级队列
    3. 工作线程从队列获取任务并执行
    4. 更新任务状态到监控器
    5. 提供任务查询和取消接口
    
    注意：此服务不修改原有的ReflectionService，而是通过组合方式使用。
    """

    def __init__(
        self,
        reflection_service: ReflectionService,
        *,
        thread_pool_size: int = 4,
        task_timeout_seconds: int = 300,
        max_retries: int = 3,
    ):
        """
        初始化异步服务
        
        Args:
            reflection_service: 底层同步反思服务
            thread_pool_size: 线程池大小
            task_timeout_seconds: 任务超时时间
            max_retries: 最大重试次数
        """
        self._reflection_service = reflection_service
        self._executor = ReflectionTaskExecutor(
            reflection_service=reflection_service,
            thread_pool_size=thread_pool_size,
            task_timeout_seconds=task_timeout_seconds,
        )
        self._monitor = get_monitor()
        self._queue = get_task_queue()
        self._max_retries = max_retries
        self._worker_running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        logger.info("AsyncReflectionService initialized")

    def start_worker(self) -> None:
        """启动后台工作线程"""
        if self._worker_running:
            logger.warning("Worker already running")
            return
        
        self._worker_running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="reflection-worker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("Reflection worker started")

    def stop_worker(self) -> None:
        """停止后台工作线程"""
        self._worker_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        self._executor.shutdown()
        logger.info("Reflection worker stopped")

    def submit_reflection_task(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any],
        trigger: ReflectionTrigger = ReflectionTrigger.AUTOMATIC,
        priority: TaskPriority = TaskPriority.NORMAL,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> str:
        """
        提交反思任务（异步）
        
        Args:
            subject: 反思主题
            reflection_type: 反思类型
            context: 反思上下文
            trigger: 触发器
            priority: 优先级
            trace_id: 追踪ID
            session_id: 会话ID
            template_id: 模板ID
        
        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())
        
        # 注册到监控器
        self._monitor.register_task(
            task_id=task_id,
            task_type=TaskType.REFLECTION,
            subtype=reflection_type.value,
            priority=int(priority),
            payload={
                "subject": subject,
                "context_keys": list(context.keys()),
                "trigger": trigger.value,
            },
            max_retries=self._max_retries,
        )
        
        # 提交到队列
        task_data = {
            "task_id": task_id,
            "subject": subject,
            "reflection_type": reflection_type,
            "context": context,
            "trigger": trigger,
            "trace_id": trace_id,
            "session_id": session_id,
            "template_id": template_id,
        }
        
        success = self._queue.put(task_id, task_data, priority=priority)
        if not success:
            self._monitor.update_status(
                task_id,
                TaskStatus.FAILED,
                error_message="Queue full, task rejected"
            )
            raise RuntimeError("Task queue is full")
        
        # 更新状态为PENDING
        self._monitor.update_status(task_id, TaskStatus.PENDING)
        
        logger.info(f"Reflection task submitted: {task_id} (priority={priority.name})")
        return task_id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务状态信息
        """
        task = self._monitor.get_task(task_id)
        if task is None:
            return {"error": "Task not found"}
        
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "progress": task.progress,
            "retry_count": task.retry_count,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "duration_ms": task.duration_ms,
            "result": task.result,
            "error_message": task.error_message,
        }

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功取消
        """
        task = self._monitor.get_task(task_id)
        if task is None:
            return False
        
        if task.status != TaskStatus.PENDING:
            logger.warning(f"Cannot cancel task {task_id} with status {task.status.value}")
            return False
        
        # 从队列中移除
        removed = self._queue.remove(task_id)
        if removed:
            self._monitor.update_status(task_id, TaskStatus.CANCELLED)
            logger.info(f"Task cancelled: {task_id}")
            return True
        
        return False

    def list_tasks(
        self,
        *,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        列出任务
        
        Args:
            status: 过滤状态
            limit: 返回数量
            offset: 偏移量
        
        Returns:
            任务列表
        """
        tasks = self._monitor.list_tasks(
            task_type=TaskType.REFLECTION,
            status=status,
            limit=limit,
            offset=offset,
        )
        
        return [task.to_dict() for task in tasks]

    def _worker_loop(self) -> None:
        """工作线程循环"""
        logger.info("Reflection worker loop started")
        
        while self._worker_running:
            try:
                # 从队列获取任务
                result = self._queue.get(timeout=1.0)
                if result is None:
                    continue
                
                task_id, task_data = result
                self._execute_task(task_id, task_data)
            
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)
        
        logger.info("Reflection worker loop stopped")

    def _execute_task(self, task_id: str, task_data: Dict[str, Any]) -> None:
        """
        执行单个任务
        
        Args:
            task_id: 任务ID
            task_data: 任务数据
        """
        # 检查是否被取消
        if task_data.get("_cancelled"):
            logger.info(f"Task {task_id} was cancelled, skipping")
            return
        
        # 更新状态为RUNNING
        self._monitor.update_status(task_id, TaskStatus.RUNNING)
        
        # 提交到执行器
        future = self._executor.submit_task(
            task_id=task_id,
            subject=task_data["subject"],
            reflection_type=task_data["reflection_type"],
            context=task_data["context"],
            trigger=task_data["trigger"],
            trace_id=task_data.get("trace_id"),
            session_id=task_data.get("session_id"),
            template_id=task_data.get("template_id"),
        )
        
        # 等待完成（带超时）
        try:
            result = future.result(timeout=self._executor._task_timeout)
            
            if result.get("success"):
                self._monitor.update_status(
                    task_id,
                    TaskStatus.COMPLETED,
                    result=result.get("result"),
                    progress=100.0,
                )
            else:
                # 失败，检查是否需要重试
                task = self._monitor.get_task(task_id)
                if task and task.retry_count < task.max_retries:
                    self._retry_task(task_id, task_data, result.get("error"))
                else:
                    self._monitor.update_status(
                        task_id,
                        TaskStatus.FAILED,
                        error_message=result.get("error"),
                        error_type=result.get("error_type"),
                    )
        
        except TimeoutError:
            logger.error(f"Task {task_id} timed out")
            self._monitor.update_status(
                task_id,
                TaskStatus.FAILED,
                error_message=f"Task timeout after {self._executor._task_timeout}s",
                error_type="TimeoutError",
            )
        
        except Exception as e:
            logger.error(f"Task {task_id} execution error: {e}", exc_info=True)
            self._monitor.update_status(
                task_id,
                TaskStatus.FAILED,
                error_message=str(e),
                error_type=type(e).__name__,
            )

    def _retry_task(self, task_id: str, task_data: Dict[str, Any], error: str) -> None:
        """
        重试任务
        
        Args:
            task_id: 任务ID
            task_data: 任务数据
            error: 错误信息
        """
        task = self._monitor.get_task(task_id)
        if task is None:
            return
        
        # 增加重试计数
        retry_count = task.retry_count + 1
        self._monitor.update_status(
            task_id,
            TaskStatus.PENDING,
            retry_count=retry_count,
            error_message=f"Retry {retry_count}/{task.max_retries}: {error}",
        )
        
        # 重新提交到队列（降低优先级）
        new_priority = min(int(task.priority) + 1, 3)
        self._queue.put(task_id, task_data, priority=TaskPriority(new_priority))
        
        logger.info(f"Task {task_id} retried ({retry_count}/{task.max_retries})")

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        monitor_metrics = self._monitor.get_metrics()
        executor_stats = self._executor.get_stats()
        queue_stats = self._queue.get_stats()
        
        return {
            "monitor": {
                "total_tasks": monitor_metrics.total_tasks,
                "success_rate": monitor_metrics.success_rate,
                "failure_rate": monitor_metrics.failure_rate,
                "avg_duration_ms": monitor_metrics.avg_duration_ms,
            },
            "executor": executor_stats,
            "queue": queue_stats,
        }

    def shutdown(self) -> None:
        """关闭服务"""
        logger.info("Shutting down AsyncReflectionService...")
        self.stop_worker()
        logger.info("AsyncReflectionService shutdown complete")
