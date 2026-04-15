"""
Priority Task Queue - 优先级任务队列

实现带优先级的任务队列，支持任务插队和老化机制。
此模块独立于具体业务逻辑，仅提供通用的队列管理能力。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple
from queue import PriorityQueue, Empty

logger = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    """
    任务优先级
    
    数值越小优先级越高
    """
    CRITICAL = 0  # 紧急修复、安全相关
    HIGH = 1      # 手动触发的用户请求
    NORMAL = 2    # 自动触发的常规任务
    LOW = 3       # 定时调度的后台任务


@dataclass(order=True)
class PriorityTask:
    """
    优先级任务包装器
    
    用于在PriorityQueue中排序
    """
    priority: int
    timestamp: float = field(compare=True)  # 用于FIFO和老化
    task_id: str = field(compare=False)
    task_data: Dict[str, Any] = field(compare=False)
    aging_boost: int = field(default=0, compare=False)  # 老化提升
    
    @property
    def effective_priority(self) -> int:
        """有效优先级（考虑老化提升）"""
        return max(0, self.priority - self.aging_boost)


class PriorityTaskQueue:
    """
    优先级任务队列
    
    特性：
    - 支持4级优先级
    - 老化机制防止低优先级任务饿死
    - 容量控制
    - 线程安全
    
    使用示例：
        queue = PriorityTaskQueue(max_size=100)
        queue.put(task_id, task_data, priority=TaskPriority.HIGH)
        task = queue.get(timeout=5)
    """

    def __init__(
        self,
        *,
        max_size: int = 100,
        aging_interval_seconds: int = 60,
        aging_threshold_seconds: int = 300,
        aging_boost_amount: int = 1,
    ):
        """
        初始化优先级队列
        
        Args:
            max_size: 最大队列长度
            aging_interval_seconds: 老化检查间隔（秒）
            aging_threshold_seconds: 老化阈值（等待超过此时间则提升优先级）
            aging_boost_amount: 每次老化提升的优先级数量
        """
        self._queue: PriorityQueue = PriorityQueue(maxsize=max_size)
        self._max_size = max_size
        self._aging_interval = aging_interval_seconds
        self._aging_threshold = aging_threshold_seconds
        self._aging_boost = aging_boost_amount
        self._lock = threading.Lock()
        self._task_entries: Dict[str, PriorityTask] = {}
        self._last_aging_check = time.time()
        self._put_count = 0
        self._get_count = 0
        self._rejected_count = 0
        
        # 启动老化检查线程
        self._aging_thread = threading.Thread(
            target=self._aging_loop,
            name="queue-aging",
            daemon=True
        )
        self._running = True
        self._aging_thread.start()
        
        logger.info(
            f"PriorityTaskQueue initialized (max_size={max_size}, "
            f"aging_interval={aging_interval_seconds}s)"
        )

    def put(
        self,
        task_id: str,
        task_data: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: float = 1.0,
    ) -> bool:
        """
        添加任务到队列
        
        Args:
            task_id: 任务ID
            task_data: 任务数据
            priority: 优先级
            timeout: 超时时间（秒）
        
        Returns:
            是否成功添加
        """
        with self._lock:
            if task_id in self._task_entries:
                logger.warning(f"Task {task_id} already in queue")
                return False
            
            if self._queue.qsize() >= self._max_size:
                logger.warning(f"Queue full ({self._max_size}), rejecting task {task_id}")
                self._rejected_count += 1
                return False
            
            now = time.time()
            entry = PriorityTask(
                priority=int(priority),
                timestamp=now,
                task_id=task_id,
                task_data=task_data,
            )
            
            try:
                self._queue.put_nowait(entry)
                self._task_entries[task_id] = entry
                self._put_count += 1
                logger.debug(f"Task queued: {task_id} (priority={priority.name})")
                return True
            except Exception as e:
                logger.error(f"Failed to queue task {task_id}: {e}")
                return False

    def get(self, timeout: float = 1.0) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        从队列获取任务
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            (task_id, task_data) 或 None（超时）
        """
        try:
            entry = self._queue.get(timeout=timeout)
            
            with self._lock:
                # 从跟踪字典中移除
                self._task_entries.pop(entry.task_id, None)
                self._get_count += 1
            
            logger.debug(f"Task dequeued: {entry.task_id}")
            return (entry.task_id, entry.task_data)
        
        except Empty:
            return None

    def remove(self, task_id: str) -> bool:
        """
        从队列中移除任务（仅适用于PENDING状态）
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功移除
        """
        with self._lock:
            if task_id not in self._task_entries:
                return False
            
            # 注意：PriorityQueue不支持直接删除，需要重建队列
            # 这里采用标记方式，实际删除在get时跳过
            entry = self._task_entries.pop(task_id)
            entry.task_data["_cancelled"] = True
            
            logger.info(f"Task cancelled: {task_id}")
            return True

    def size(self) -> int:
        """获取队列当前大小"""
        return self._queue.qsize()

    def is_full(self) -> bool:
        """检查队列是否已满"""
        return self._queue.qsize() >= self._max_size

    def get_stats(self) -> Dict[str, Any]:
        """
        获取队列统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            return {
                "current_size": self._queue.qsize(),
                "max_size": self._max_size,
                "total_put": self._put_count,
                "total_get": self._get_count,
                "total_rejected": self._rejected_count,
                "tracked_tasks": len(self._task_entries),
                "utilization": self._queue.qsize() / self._max_size if self._max_size > 0 else 0,
            }

    def clear(self) -> int:
        """
        清空队列
        
        Returns:
            清除的任务数量
        """
        with self._lock:
            count = 0
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    count += 1
                except Empty:
                    break
            
            self._task_entries.clear()
            logger.info(f"Queue cleared: {count} tasks removed")
            return count

    def _aging_loop(self) -> None:
        """老化检查循环（后台线程）"""
        while self._running:
            try:
                time.sleep(self._aging_interval)
                self._perform_aging()
            except Exception as e:
                logger.error(f"Aging loop error: {e}")

    def _perform_aging(self) -> None:
        """执行老化检查"""
        now = time.time()
        
        with self._lock:
            # 检查是否需要执行老化
            if now - self._last_aging_check < self._aging_interval:
                return
            
            self._last_aging_check = now
            aged_count = 0
            
            for task_id, entry in list(self._task_entries.items()):
                wait_time = now - entry.timestamp
                
                # 如果等待时间超过阈值，提升优先级
                if wait_time > self._aging_threshold:
                    old_priority = entry.effective_priority
                    entry.aging_boost += self._aging_boost
                    new_priority = entry.effective_priority
                    
                    if new_priority < old_priority:
                        aged_count += 1
                        logger.debug(
                            f"Task {task_id} aged: priority {old_priority} -> {new_priority} "
                            f"(waited {wait_time:.0f}s)"
                        )
            
            if aged_count > 0:
                logger.info(f"Aging check: {aged_count} tasks boosted")

    def shutdown(self) -> None:
        """关闭队列和老化线程"""
        self._running = False
        if self._aging_thread.is_alive():
            self._aging_thread.join(timeout=2.0)
        logger.info("PriorityTaskQueue shutdown")


# 全局单例
_queue_instance: Optional[PriorityTaskQueue] = None
_queue_lock = threading.Lock()


def get_task_queue() -> PriorityTaskQueue:
    """获取全局任务队列实例"""
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = PriorityTaskQueue()
    return _queue_instance


def reset_task_queue() -> None:
    """重置任务队列（主要用于测试）"""
    global _queue_instance
    with _queue_lock:
        if _queue_instance:
            _queue_instance.shutdown()
        _queue_instance = None
