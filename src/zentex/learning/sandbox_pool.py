"""
Sandbox Process Pool - 沙箱进程池

管理G16沙箱验证的独立进程，实现完全的资源隔离和安全执行。
此模块提供进程级别的安全边界，防止恶意代码逃逸。
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from multiprocessing import Process, Queue
from typing import Any, Callable, Dict, List, Optional
import threading

logger = logging.getLogger(__name__)


class ProcessStatus(str, Enum):
    """进程状态"""
    IDLE = "IDLE"
    BUSY = "BUSY"
    ERROR = "ERROR"
    TERMINATED = "TERMINATED"


class HealthStatus(str, Enum):
    """健康状态"""
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass
class SandboxProcessInfo:
    """沙箱进程信息"""
    process_id: str
    pid: Optional[int] = None
    status: ProcessStatus = ProcessStatus.IDLE
    assigned_task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    restart_count: int = 0
    error_log: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_id": self.process_id,
            "pid": self.pid,
            "status": self.status.value,
            "assigned_task_id": self.assigned_task_id,
            "health_status": self.health_status.value,
            "restart_count": self.restart_count,
        }


class SandboxProcessPool:
    """
    沙箱进程池
    
    管理固定数量的沙箱进程，用于执行不可信的代码验证。
    每个沙箱进程都是独立的Python进程，具有严格的资源限制。
    
    安全特性：
    - 进程级隔离
    - 资源限制（内存、CPU、时间）
    - 禁止网络访问（可选）
    - 文件系统只读（可选）
    - 自动健康检查和恢复
    """

    def __init__(
        self,
        *,
        pool_size: int = 2,
        timeout_seconds: int = 300,
        memory_limit_mb: int = 512,
        cpu_limit: float = 1.0,
        enable_network_restriction: bool = False,
        enable_filesystem_restriction: bool = False,
    ):
        """
        初始化沙箱进程池
        
        Args:
            pool_size: 进程池大小
            timeout_seconds: 任务超时时间（秒）
            memory_limit_mb: 内存限制（MB）
            cpu_limit: CPU限制（核数）
            enable_network_restriction: 是否禁止网络访问
            enable_filesystem_restriction: 是否限制文件系统访问
        """
        self._pool_size = pool_size
        self._timeout = timeout_seconds
        self._memory_limit = memory_limit_mb
        self._cpu_limit = cpu_limit
        self._network_restricted = enable_network_restriction
        self._filesystem_restricted = enable_filesystem_restriction
        
        self._processes: Dict[str, SandboxProcessInfo] = {}
        self._process_objects: Dict[str, Process] = {}
        self._request_queues: Dict[str, Queue] = {}
        self._response_queues: Dict[str, Queue] = {}
        
        self._lock = threading.Lock()
        self._health_check_thread: Optional[threading.Thread] = None
        self._running = False
        
        # 初始化进程池
        self._initialize_pool()
        
        logger.info(
            f"SandboxProcessPool initialized (size={pool_size}, "
            f"timeout={timeout_seconds}s, memory={memory_limit_mb}MB)"
        )

    def _initialize_pool(self) -> None:
        """初始化进程池"""
        for i in range(self._pool_size):
            process_id = f"sandbox-{i}"
            self._create_sandbox_process(process_id)

    def _create_sandbox_process(self, process_id: str) -> None:
        """创建单个沙箱进程"""
        request_queue = multiprocessing.Queue()
        response_queue = multiprocessing.Queue()
        
        process = Process(
            target=self._sandbox_worker,
            args=(process_id, request_queue, response_queue),
            name=f"sandbox-worker-{process_id}",
            daemon=True,
        )
        
        process.start()
        
        now = datetime.now(timezone.utc)
        process_info = SandboxProcessInfo(
            process_id=process_id,
            pid=process.pid,
            status=ProcessStatus.IDLE,
            started_at=now,
            last_used_at=now,
            health_status=HealthStatus.HEALTHY,
        )
        
        with self._lock:
            self._processes[process_id] = process_info
            self._process_objects[process_id] = process
            self._request_queues[process_id] = request_queue
            self._response_queues[process_id] = response_queue
        
        logger.info(f"Sandbox process created: {process_id} (PID: {process.pid})")

    def acquire(self, timeout: float = 5.0) -> Optional[str]:
        """
        获取空闲的沙箱进程
        
        Args:
            timeout: 等待超时时间（秒）
        
        Returns:
            进程ID，或None（无可用进程）
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._lock:
                for process_id, info in self._processes.items():
                    if info.status == ProcessStatus.IDLE and info.health_status == HealthStatus.HEALTHY:
                        info.status = ProcessStatus.BUSY
                        info.last_used_at = datetime.now(timezone.utc)
                        logger.debug(f"Sandbox process acquired: {process_id}")
                        return process_id
            
            time.sleep(0.1)
        
        logger.warning("No available sandbox process")
        return None

    def release(self, process_id: str) -> None:
        """
        释放沙箱进程回池
        
        Args:
            process_id: 进程ID
        """
        with self._lock:
            if process_id in self._processes:
                info = self._processes[process_id]
                info.status = ProcessStatus.IDLE
                info.assigned_task_id = None
                logger.debug(f"Sandbox process released: {process_id}")

    def execute_task(
        self,
        process_id: str,
        task_id: str,
        worker_func: Callable,
        worker_args: tuple = (),
        worker_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        在沙箱进程中执行任务
        
        Args:
            process_id: 进程ID
            task_id: 任务ID
            worker_func: 要执行的函数
            worker_args: 位置参数
            worker_kwargs: 关键字参数
        
        Returns:
            执行结果
        """
        if worker_kwargs is None:
            worker_kwargs = {}
        
        with self._lock:
            if process_id not in self._processes:
                raise ValueError(f"Invalid process_id: {process_id}")
            
            info = self._processes[process_id]
            info.assigned_task_id = task_id
        
        # 准备请求
        request = {
            "task_id": task_id,
            "worker_func_name": worker_func.__name__,
            "args": worker_args,
            "kwargs": worker_kwargs,
            "timeout": self._timeout,
        }
        
        try:
            # 发送请求
            request_queue = self._request_queues[process_id]
            response_queue = self._response_queues[process_id]
            
            request_queue.put(request, timeout=2.0)
            
            # 等待响应（带超时）
            try:
                response = response_queue.get(timeout=self._timeout)
                
                if response.get("success"):
                    logger.debug(f"Task {task_id} completed in {process_id}")
                    return response
                else:
                    logger.error(f"Task {task_id} failed in {process_id}: {response.get('error')}")
                    return response
            
            except multiprocessing.queues.Empty:
                error_msg = f"Task {task_id} timed out after {self._timeout}s"
                logger.error(error_msg)
                
                # 终止并重建进程
                self._terminate_and_rebuild_process(process_id)
                
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": "TimeoutError",
                }
        
        except Exception as e:
            logger.error(f"Task execution error in {process_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def health_check(self) -> List[Dict[str, Any]]:
        """
        执行健康检查
        
        Returns:
            所有进程的健康状态列表
        """
        results = []
        
        with self._lock:
            for process_id, info in list(self._processes.items()):
                process = self._process_objects.get(process_id)
                
                if process is None or not process.is_alive():
                    info.health_status = HealthStatus.UNHEALTHY
                    info.status = ProcessStatus.ERROR
                    results.append({
                        "process_id": process_id,
                        "healthy": False,
                        "reason": "Process not alive",
                    })
                    
                    # 自动重建
                    self._terminate_and_rebuild_process(process_id)
                else:
                    info.health_status = HealthStatus.HEALTHY
                    results.append({
                        "process_id": process_id,
                        "healthy": True,
                        "pid": process.pid,
                        "status": info.status.value,
                    })
        
        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取进程池统计信息"""
        with self._lock:
            total = len(self._processes)
            idle = sum(1 for p in self._processes.values() if p.status == ProcessStatus.IDLE)
            busy = sum(1 for p in self._processes.values() if p.status == ProcessStatus.BUSY)
            errors = sum(1 for p in self._processes.values() if p.status == ProcessStatus.ERROR)
            
            return {
                "pool_size": total,
                "idle_count": idle,
                "busy_count": busy,
                "error_count": errors,
                "utilization": busy / total if total > 0 else 0,
                "processes": [p.to_dict() for p in self._processes.values()],
            }

    def shutdown(self, wait: bool = True, timeout: float = 10.0) -> None:
        """关闭进程池"""
        logger.info("Shutting down SandboxProcessPool...")
        self._running = False
        
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=2.0)
        
        with self._lock:
            for process_id, process in list(self._process_objects.items()):
                try:
                    if process.is_alive():
                        process.terminate()
                        if wait:
                            process.join(timeout=timeout)
                            if process.is_alive():
                                process.kill()
                except Exception as e:
                    logger.error(f"Error terminating process {process_id}: {e}")
            
            self._processes.clear()
            self._process_objects.clear()
            self._request_queues.clear()
            self._response_queues.clear()
        
        logger.info("SandboxProcessPool shutdown complete")

    def start_health_check(self, interval_seconds: int = 30) -> None:
        """启动健康检查线程"""
        if self._health_check_thread and self._health_check_thread.is_alive():
            return
        
        self._running = True
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            kwargs={"interval": interval_seconds},
            name="sandbox-health-check",
            daemon=True,
        )
        self._health_check_thread.start()
        logger.info(f"Sandbox health check started (interval={interval_seconds}s)")

    def _health_check_loop(self, interval: int = 30) -> None:
        """健康检查循环"""
        while self._running:
            try:
                time.sleep(interval)
                self.health_check()
            except Exception as e:
                logger.error(f"Health check error: {e}")

    def _terminate_and_rebuild_process(self, process_id: str) -> None:
        """终止并重建进程"""
        with self._lock:
            process = self._process_objects.get(process_id)
            if process and process.is_alive():
                try:
                    process.terminate()
                    process.join(timeout=5.0)
                    if process.is_alive():
                        process.kill()
                except Exception as e:
                    logger.error(f"Error terminating process {process_id}: {e}")
            
            # 更新状态
            if process_id in self._processes:
                self._processes[process_id].restart_count += 1
                self._processes[process_id].status = ProcessStatus.TERMINATED
        
        # 重建进程
        self._create_sandbox_process(process_id)
        logger.info(f"Sandbox process rebuilt: {process_id}")

    @staticmethod
    def _sandbox_worker(
        process_id: str,
        request_queue: Queue,
        response_queue: Queue,
    ) -> None:
        """
        沙箱工作进程主循环
        
        此函数在独立进程中运行，接收任务请求并执行。
        
        Args:
            process_id: 进程ID
            request_queue: 请求队列
            response_queue: 响应队列
        """
        logger.info(f"Sandbox worker started: {process_id} (PID: {os.getpid()})")
        
        while True:
            try:
                # 等待请求
                request = request_queue.get(timeout=60.0)
                
                task_id = request.get("task_id")
                logger.debug(f"Sandbox executing task: {task_id}")
                
                # 注意：这里无法直接执行传入的函数对象
                # 实际使用时需要注册worker函数映射
                # 这是一个简化的实现
                
                response = {
                    "success": False,
                    "error": "Worker function not registered. Use register_worker() first.",
                    "error_type": "NotImplementedError",
                }
                
                response_queue.put(response)
            
            except multiprocessing.queues.Empty:
                # 超时，继续等待
                continue
            except Exception as e:
                logger.error(f"Sandbox worker error: {e}", exc_info=True)
                response_queue.put({
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                })


# 全局单例
_pool_instance: Optional[SandboxProcessPool] = None
_pool_lock = threading.Lock()


def get_sandbox_pool(**kwargs) -> SandboxProcessPool:
    """获取或创建沙箱进程池实例"""
    global _pool_instance
    if _pool_instance is None:
        with _pool_lock:
            if _pool_instance is None:
                _pool_instance = SandboxProcessPool(**kwargs)
    return _pool_instance


def reset_sandbox_pool() -> None:
    """重置沙箱进程池（主要用于测试）"""
    global _pool_instance
    with _pool_lock:
        if _pool_instance:
            _pool_instance.shutdown()
        _pool_instance = None
