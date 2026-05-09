from __future__ import annotations
"""
Reflection Task Executor - 反思任务执行器

负责在后台线程池中执行反思生成任务。
此模块独立于Web层，仅提供任务执行能力。
"""


import logging
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timezone

from zentex.reflection.models import ReflectionType, ReflectionTrigger
from zentex.reflection.service import ReflectionService

logger = logging.getLogger(__name__)


class ReflectionTaskExecutor:
    """
    反思任务执行器
    
    使用专用线程池执行反思生成任务，避免阻塞主线程。
    与监控器和队列集成，提供完整的任务生命周期管理。
    """

    def __init__(
        self,
        *,
        reflection_service: ReflectionService,
        thread_pool_size: int = 4,
        task_timeout_seconds: int = 300,
    ):
        """
        初始化执行器
        
        Args:
            reflection_service: 反思服务实例
            thread_pool_size: 线程池大小
            task_timeout_seconds: 任务超时时间（秒）
        """
        self._reflection_service = reflection_service
        self._thread_pool = ThreadPoolExecutor(
            max_workers=thread_pool_size,
            thread_name_prefix="reflection-executor"
        )
        self._task_timeout = task_timeout_seconds
        self._active_tasks: Dict[str, Future] = {}
        self._lock = threading.Lock()
        
        logger.info(
            f"ReflectionTaskExecutor initialized "
            f"(pool_size={thread_pool_size}, timeout={task_timeout_seconds}s)"
        )

    def submit_task(
        self,
        task_id: str,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any],
        trigger: ReflectionTrigger = ReflectionTrigger.AUTOMATIC,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Future:
        """
        提交反思任务到线程池
        
        Args:
            task_id: 任务ID
            subject: 反思主题
            reflection_type: 反思类型
            context: 反思上下文
            trigger: 触发器
            trace_id: 追踪ID
            session_id: 会话ID
            template_id: 模板ID
        
        Returns:
            Future对象
        """
        def _execute():
            try:
                logger.info(f"Executing reflection task: {task_id}")
                
                # 调用原有的同步服务
                result = self._reflection_service.generate_reflection(
                    subject=subject,
                    reflection_type=reflection_type,
                    context=context,
                    trigger=trigger,
                    trace_id=trace_id,
                    session_id=session_id,
                    template_id=template_id,
                )
                
                logger.info(f"Reflection task completed: {task_id}")
                return {
                    "success": True,
                    "result": result.to_dict() if hasattr(result, 'to_dict') else result,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            
            except Exception as e:
                logger.error(f"Reflection task failed: {task_id}, error: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
        
        future = self._thread_pool.submit(_execute)
        
        with self._lock:
            self._active_tasks[task_id] = future
        
        # 添加完成回调
        future.add_done_callback(lambda f: self._on_task_complete(task_id, f))
        
        return future

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务（仅对未开始的任务有效）
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功取消
        """
        with self._lock:
            future = self._active_tasks.get(task_id)
            if future is None:
                return False
            
            cancelled = future.cancel()
            if cancelled:
                del self._active_tasks[task_id]
                logger.info(f"Reflection task cancelled: {task_id}")
            
            return cancelled

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务状态信息
        """
        with self._lock:
            future = self._active_tasks.get(task_id)
        
        if future is None:
            return {"status": "unknown", "message": "Task not found"}
        
        if future.cancelled():
            return {"status": "cancelled"}
        
        if future.done():
            try:
                result = future.result(timeout=0)
                if result.get("success"):
                    return {"status": "completed", "result": result}
                else:
                    return {"status": "failed", "error": result.get("error")}
            except Exception as e:
                return {"status": "failed", "error": str(e)}
        
        return {"status": "running"}

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """
        关闭执行器
        
        Args:
            wait: 是否等待正在执行的任务完成
            timeout: 等待超时时间（秒）
        """
        logger.info("Shutting down ReflectionTaskExecutor...")
        self._thread_pool.shutdown(wait=wait, cancel_futures=not wait)
        logger.info("ReflectionTaskExecutor shutdown complete")

    def _on_task_complete(self, task_id: str, future: Future) -> None:
        """任务完成回调"""
        with self._lock:
            self._active_tasks.pop(task_id, None)
        
        try:
            result = future.result(timeout=0)
            if result.get("success"):
                logger.debug(f"Task {task_id} completed successfully")
            else:
                logger.warning(f"Task {task_id} failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"Task {task_id} callback error: {e}")

    @property
    def active_task_count(self) -> int:
        """活跃任务数量"""
        with self._lock:
            return len(self._active_tasks)

    def get_stats(self) -> Dict[str, Any]:
        """获取执行器统计信息"""
        with self._lock:
            return {
                "active_tasks": len(self._active_tasks),
                "thread_pool_size": self._thread_pool._max_workers,
                "task_timeout_seconds": self._task_timeout,
            }


# 全局单例（可选，通常通过依赖注入使用）
_executor_instance: Optional[ReflectionTaskExecutor] = None
_executor_lock = threading.Lock()


def get_reflection_executor(reflection_service: ReflectionService, **kwargs) -> ReflectionTaskExecutor:
    """获取或创建执行器实例"""
    global _executor_instance
    if _executor_instance is None:
        with _executor_lock:
            if _executor_instance is None:
                _executor_instance = ReflectionTaskExecutor(
                    reflection_service=reflection_service,
                    **kwargs
                )
    return _executor_instance


def reset_reflection_executor() -> None:
    """重置执行器（主要用于测试）"""
    global _executor_instance
    with _executor_lock:
        if _executor_instance:
            _executor_instance.shutdown()
        _executor_instance = None
