from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone

from zentex.tasks.models import (
    ZentexTask, TaskStatus, TaskType, TaskPriority, 
    SuspendedTask, TaskContract, TaskStateError
)
from zentex.tasks.service import TaskManagementService
from zentex.tasks.registry import TaskRegistry
from zentex.tasks.core import TaskDecomposerPlugin

logger = logging.getLogger(__name__)

class TaskServiceInterface:
    """
    统一的任务管理对外服务接口
    
    提供标准化的任务管理服务，供其他模块安全接入。
    所有操作都经过验证、审计和错误处理。
    """
    
    def __init__(self, task_service: TaskManagementService) -> None:
        """
        初始化任务服务接口
        
        Args:
            task_service: 任务管理服务实例
        """
        self._service = task_service
        self._interface_name = "TaskServiceInterface"
        logger.info(f"{self._interface_name} initialized")
    
    # === 基础任务操作 ===
    
    async def create_task(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建任务
        
        Args:
            request: 任务创建请求，包含必需字段
            
        Returns:
            创建结果和任务信息
        """
        try:
            # 验证必需字段
            required_fields = ["title", "task_type", "originator_id"]
            for field in required_fields:
                if field not in request:
                    return {
                        "success": False,
                        "error": f"Missing required field: {field}",
                        "error_code": "MISSING_FIELD"
                    }
            
            # 创建任务
            task = await self._service.create_task(request)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Task {task.task_id} created successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "CREATION_FAILED"
            }
    
    async def create_mission(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建任务（使命类型）
        
        Args:
            request: 使命创建请求
            
        Returns:
            创建结果
        """
        request["task_type"] = TaskType.MISSION
        return await self.create_task(request)
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息或错误
        """
        try:
            task = self._service.get_task(task_id)
            if not task:
                return {
                    "success": False,
                    "error": f"Task {task_id} not found",
                    "error_code": "NOT_FOUND"
                }
            
            return {
                "success": True,
                "task": task.model_dump()
            }
            
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "RETRIEVAL_FAILED"
            }
    
    def list_tasks(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        列出任务
        
        Args:
            filters: 过滤条件
            
        Returns:
            任务列表
        """
        try:
            filters = filters or {}
            
            tasks = self._service.list_tasks(
                status=filters.get("status"),
                priority=filters.get("priority"),
                tags=filters.get("tags"),
                parent_task_id=filters.get("parent_task_id"),
                target_id=filters.get("target_id"),
                overdue_only=filters.get("overdue_only", False),
                source_module=filters.get("source_module"),
                metadata_filters=filters.get("metadata_filters"),
            )
            
            return {
                "success": True,
                "tasks": [task.model_dump() for task in tasks],
                "count": len(tasks)
            }
            
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "LIST_FAILED"
            }
    
    def update_task_status(self, task_id: str, status: str, remarks: Optional[str] = None) -> Dict[str, Any]:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            remarks: 备注信息
            
        Returns:
            更新结果
        """
        try:
            # 验证状态
            try:
                new_status = TaskStatus(status)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid status: {status}",
                    "error_code": "INVALID_STATUS"
                }
            
            task = self._service.update_task_status(task_id, new_status, remarks)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Task {task_id} status updated to {status}"
            }
            
        except TaskStateError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": "INVALID_STATE_TRANSITION"
            }
        except Exception as e:
            logger.error(f"Failed to update task status {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "UPDATE_FAILED"
            }
    
    def claim_task(self, task_id: str, handler_id: str) -> Dict[str, Any]:
        """
        认领任务
        
        Args:
            task_id: 任务ID
            handler_id: 处理者ID
            
        Returns:
            认领结果
        """
        try:
            task = self._service.claim_task(task_id, handler_id)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Task {task_id} claimed by {handler_id}"
            }
            
        except Exception as e:
            logger.error(f"Failed to claim task {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "CLAIM_FAILED"
            }
    
    # === 优先级和截止时间管理 ===
    
    def set_task_priority(self, task_id: str, priority: str) -> Dict[str, Any]:
        """
        设置任务优先级
        
        Args:
            task_id: 任务ID
            priority: 优先级
            
        Returns:
            设置结果
        """
        try:
            try:
                priority_enum = TaskPriority(priority)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid priority: {priority}",
                    "error_code": "INVALID_PRIORITY"
                }
            
            task = self._service.set_task_priority(task_id, priority_enum)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Task {task_id} priority set to {priority}"
            }
            
        except Exception as e:
            logger.error(f"Failed to set task priority {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "PRIORITY_SET_FAILED"
            }
    
    def set_task_deadline(self, task_id: str, deadline: str) -> Dict[str, Any]:
        """
        设置任务截止时间
        
        Args:
            task_id: 任务ID
            deadline: 截止时间 (ISO格式字符串)
            
        Returns:
            设置结果
        """
        try:
            # 解析截止时间
            try:
                deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid deadline format: {deadline}",
                    "error_code": "INVALID_DEADLINE"
                }
            
            task = self._service.set_task_deadline(task_id, deadline_dt)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Task {task_id} deadline set to {deadline}"
            }
            
        except Exception as e:
            logger.error(f"Failed to set task deadline {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "DEADLINE_SET_FAILED"
            }
    
    def get_overdue_tasks(self) -> Dict[str, Any]:
        """
        获取过期任务
        
        Returns:
            过期任务列表
        """
        try:
            tasks = self._service.get_overdue_tasks()
            
            return {
                "success": True,
                "tasks": [task.model_dump() for task in tasks],
                "count": len(tasks)
            }
            
        except Exception as e:
            logger.error(f"Failed to get overdue tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "OVERDUE_RETRIEVAL_FAILED"
            }
    
    # === 挂起和恢复 ===
    
    def suspend_task(self, task_id: str, reason: str, recovery_conditions: Optional[List[str]] = None, 
                    auto_resume_at: Optional[str] = None) -> Dict[str, Any]:
        """
        挂起任务
        
        Args:
            task_id: 任务ID
            reason: 挂起原因
            recovery_conditions: 恢复条件
            auto_resume_at: 自动恢复时间
            
        Returns:
            挂起结果
        """
        try:
            # 解析自动恢复时间
            resume_dt = None
            if auto_resume_at:
                try:
                    resume_dt = datetime.fromisoformat(auto_resume_at.replace('Z', '+00:00'))
                except ValueError:
                    return {
                        "success": False,
                        "error": f"Invalid auto_resume_at format: {auto_resume_at}",
                        "error_code": "INVALID_RESUME_TIME"
                    }
            
            task = self._service.suspend_task(task_id, reason, recovery_conditions, resume_dt)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Task {task_id} suspended: {reason}"
            }
            
        except Exception as e:
            logger.error(f"Failed to suspend task {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "SUSPEND_FAILED"
            }
    
    def resume_task(self, task_id: str, remarks: Optional[str] = None) -> Dict[str, Any]:
        """
        恢复任务
        
        Args:
            task_id: 任务ID
            remarks: 备注信息
            
        Returns:
            恢复结果
        """
        try:
            task = self._service.resume_task(task_id, remarks)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Task {task_id} resumed"
            }
            
        except Exception as e:
            logger.error(f"Failed to resume task {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "RESUME_FAILED"
            }
    
    def get_suspended_tasks(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        获取挂起任务列表
        
        Returns:
            挂起任务列表
        """
        try:
            suspended_tasks = self._service.list_suspended_tasks(limit=limit, offset=offset)
            
            return {
                "success": True,
                "suspended_tasks": [task.model_dump() for task in suspended_tasks],
                "count": len(suspended_tasks)
            }
            
        except Exception as e:
            logger.error(f"Failed to get suspended tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "SUSPENDED_RETRIEVAL_FAILED"
            }
    
    async def check_auto_resume(self) -> Dict[str, Any]:
        """
        检查自动恢复
        
        Returns:
            自动恢复结果
        """
        try:
            resumed_tasks = await self._service.check_auto_resume_tasks()
            
            return {
                "success": True,
                "resumed_tasks": [task.model_dump() for task in resumed_tasks],
                "count": len(resumed_tasks),
                "message": f"Auto-resumed {len(resumed_tasks)} tasks"
            }
            
        except Exception as e:
            logger.error(f"Failed to check auto resume: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "AUTO_RESUME_CHECK_FAILED"
            }
    
    # === 依赖关系管理 ===
    
    def add_dependency(self, task_id: str, dependency_id: str) -> Dict[str, Any]:
        """
        添加任务依赖
        
        Args:
            task_id: 任务ID
            dependency_id: 依赖任务ID
            
        Returns:
            添加结果
        """
        try:
            task = self._service.add_dependency(task_id, dependency_id)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Added dependency {dependency_id} to task {task_id}"
            }
            
        except Exception as e:
            logger.error(f"Failed to add dependency {task_id}->{dependency_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "DEPENDENCY_ADD_FAILED"
            }
    
    def remove_dependency(self, task_id: str, dependency_id: str) -> Dict[str, Any]:
        """
        移除任务依赖
        
        Args:
            task_id: 任务ID
            dependency_id: 依赖任务ID
            
        Returns:
            移除结果
        """
        try:
            task = self._service.remove_dependency(task_id, dependency_id)
            
            return {
                "success": True,
                "task": task.model_dump(),
                "message": f"Removed dependency {dependency_id} from task {task_id}"
            }
            
        except Exception as e:
            logger.error(f"Failed to remove dependency {task_id}->{dependency_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "DEPENDENCY_REMOVE_FAILED"
            }
    
    def get_dependency_tree(self, task_id: str, max_depth: int = 5) -> Dict[str, Any]:
        """
        获取依赖树
        
        Args:
            task_id: 任务ID
            max_depth: 最大深度
            
        Returns:
            依赖树结构
        """
        try:
            tree = self._service.get_dependency_tree(task_id, max_depth)
            
            return {
                "success": True,
                "dependency_tree": tree,
                "task_id": task_id
            }
            
        except Exception as e:
            logger.error(f"Failed to get dependency tree for {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "DEPENDENCY_TREE_FAILED"
            }
    
    def can_execute_task(self, task_id: str) -> Dict[str, Any]:
        """
        检查任务是否可执行
        
        Args:
            task_id: 任务ID
            
        Returns:
            可执行性检查结果
        """
        try:
            result = self._service.can_execute_task(task_id)
            
            return {
                "success": True,
                "can_execute": result["can_execute"],
                "reason": result["reason"],
                "dependencies_satisfied": result["dependencies_satisfied"],
                "unsatisfied_dependencies": result.get("unsatisfied_dependencies", [])
            }
            
        except Exception as e:
            logger.error(f"Failed to check executability for {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "EXECUTABILITY_CHECK_FAILED"
            }
    
    def get_ready_tasks(self) -> Dict[str, Any]:
        """
        获取准备就绪的任务
        
        Returns:
            就绪任务列表
        """
        try:
            tasks = self._service.get_ready_tasks()
            
            return {
                "success": True,
                "ready_tasks": [task.model_dump() for task in tasks],
                "count": len(tasks)
            }
            
        except Exception as e:
            logger.error(f"Failed to get ready tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "READY_TASKS_RETRIEVAL_FAILED"
            }
    
    # === 批量操作 ===
    
    def bulk_update_status(self, task_ids: List[str], status: str, remarks: Optional[str] = None) -> Dict[str, Any]:
        """
        批量更新任务状态
        
        Args:
            task_ids: 任务ID列表
            status: 新状态
            remarks: 备注信息
            
        Returns:
            批量更新结果
        """
        try:
            try:
                new_status = TaskStatus(status)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid status: {status}",
                    "error_code": "INVALID_STATUS"
                }
            
            result = self._service.bulk_update_status(task_ids, new_status, remarks)
            
            return {
                "success": True,
                "results": result,
                "success_count": len(result["success"]),
                "failed_count": len(result["failed"]),
                "message": f"Bulk updated {len(result['success'])} tasks"
            }
            
        except Exception as e:
            logger.error(f"Failed to bulk update status: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "BULK_UPDATE_FAILED"
            }
    
    def bulk_suspend(self, task_ids: List[str], reason: str, recovery_conditions: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        批量挂起任务
        
        Args:
            task_ids: 任务ID列表
            reason: 挂起原因
            recovery_conditions: 恢复条件
            
        Returns:
            批量挂起结果
        """
        try:
            result = self._service.bulk_suspend(task_ids, reason, recovery_conditions)
            
            return {
                "success": True,
                "results": result,
                "success_count": len(result["success"]),
                "failed_count": len(result["failed"]),
                "message": f"Bulk suspended {len(result['success'])} tasks"
            }
            
        except Exception as e:
            logger.error(f"Failed to bulk suspend: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "BULK_SUSPEND_FAILED"
            }
    
    def bulk_resume(self, task_ids: List[str], remarks: Optional[str] = None) -> Dict[str, Any]:
        """
        批量恢复任务
        
        Args:
            task_ids: 任务ID列表
            remarks: 备注信息
            
        Returns:
            批量恢复结果
        """
        try:
            result = self._service.bulk_resume(task_ids, remarks)
            
            return {
                "success": True,
                "results": result,
                "success_count": len(result["success"]),
                "failed_count": len(result["failed"]),
                "message": f"Bulk resumed {len(result['success'])} tasks"
            }
            
        except Exception as e:
            logger.error(f"Failed to bulk resume: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "BULK_RESUME_FAILED"
            }
    
    # === 统计和监控 ===
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Returns:
            统计信息
        """
        try:
            stats = self._service.get_task_statistics()
            
            return {
                "success": True,
                "statistics": stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get task statistics: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "STATISTICS_FAILED"
            }
    
    def get_persistence_stats(self) -> Dict[str, Any]:
        """
        获取持久化统计信息
        
        Returns:
            持久化统计
        """
        try:
            stats = self._service.get_persistence_stats()
            
            return {
                "success": True,
                "persistence_stats": stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get persistence stats: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "PERSISTENCE_STATS_FAILED"
            }
    
    def save_state(self) -> Dict[str, Any]:
        """
        手动保存状态
        
        Returns:
            保存结果
        """
        try:
            success = self._service.save_state()
            
            return {
                "success": success,
                "message": "State saved successfully" if success else "State save failed"
            }
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "SAVE_STATE_FAILED"
            }
    
    # === 干预操作 ===
    
    def intervene_task(self, task_id: str, action: str, idempotency_key: str, 
                      remarks: Optional[str] = None, operator_id: str = "system") -> Dict[str, Any]:
        """
        任务干预操作
        
        Args:
            task_id: 任务ID
            action: 干预动作
            idempotency_key: 幂等键
            remarks: 备注信息
            operator_id: 操作者ID
            
        Returns:
            干预结果
        """
        try:
            result = self._service.intervene(
                task_id, action=action, idempotency_key=idempotency_key,
                remarks=remarks, operator_id=operator_id
            )
            
            return {
                "success": True,
                "intervention_result": result,
                "message": f"Intervention {action} applied to task {task_id}"
            }
            
        except Exception as e:
            logger.error(f"Failed to intervene task {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "INTERVENTION_FAILED"
            }
    
    # === 清理操作 ===
    
    def cleanup_failed_tasks(self, force: bool = False) -> Dict[str, Any]:
        """
        清理失败任务
        
        Args:
            force: 是否强制删除
            
        Returns:
            清理结果
        """
        try:
            result = self._service.cleanup_failed_tasks(force)
            
            return {
                "success": True,
                "cleanup_result": result,
                "deleted_count": len(result["success"]),
                "message": f"Cleaned up {len(result['success'])} failed tasks"
            }
            
        except Exception as e:
            logger.error(f"Failed to cleanup failed tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "CLEANUP_FAILED"
            }
    
    def bulk_archive_completed(self, older_than_days: int = 7) -> Dict[str, Any]:
        """
        批量归档已完成任务
        
        Args:
            older_than_days: 归档多少天前的任务
            
        Returns:
            归档结果
        """
        try:
            result = self._service.bulk_archive_completed(older_than_days)
            
            return {
                "success": True,
                "archive_result": result,
                "archived_count": len(result["success"]),
                "message": f"Archived {len(result['success'])} completed tasks"
            }
            
        except Exception as e:
            logger.error(f"Failed to bulk archive completed: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "BULK_ARCHIVE_FAILED"
            }
    
    # === Verification Operations ===
    
    async def complete_task_with_verification(
        self, 
        task_id: str, 
        result: Dict[str, Any],
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete a task with verification workflow.
        
        Args:
            task_id: Task ID
            result: Worker's submission result
            remarks: Optional remarks
            
        Returns:
            Completion result with verification details
        """
        try:
            return await self._service.complete_task_with_verification(
                task_id, result, remarks
            )
        except Exception as e:
            logger.error(f"Failed to complete task with verification {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "VERIFICATION_COMPLETION_FAILED"
            }
    
    def get_verification_engine_status(self) -> Dict[str, Any]:
        """
        Get verification engine status.
        
        Returns:
            Verification engine status information
        """
        try:
            return self._service.get_verification_engine_status()
        except Exception as e:
            logger.error(f"Failed to get verification engine status: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "VERIFICATION_STATUS_FAILED"
            }
