from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from zentex.tasks.models import ZentexTask, TaskStatus, TaskType, TaskScope, TaskPriority, SuspendedTask
from zentex.tasks.management.task_management_service import (
    LLMTaskDecomposerPlugin,
    PydanticAITaskDecomposerPlugin,
    TaskAutoLoopScheduler,
    TaskManagementService,
    get_service,
    recover_waiting_confirmation_task,
    task_plugin_check_constraints,
    task_plugin_extract_evidence,
    task_plugin_match_capabilities,
    task_plugin_normalize_result,
    task_plugin_plan_compensation,
    task_plugin_rule_based_verification,
    verify_external_side_effect,
    verify_writeback_content,
)
from zentex.tasks.service import TaskManagementServiceInterface
from zentex.tasks.registry import TaskRegistry
from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.models.errors import TaskStateError
from zentex.tasks.core.interface import TaskServiceInterface
from zentex.tasks.registry.plugin_registry_llm import create_default_task_plugin_registry

logger = logging.getLogger(__name__)

class TaskManager:
    """
    High-level task management interface.
    Provides simplified access to task operations with sensible defaults.
    """
    
    def __init__(
        self,
        transcript_store: Any,
        storage_path: Optional[str] = None,
        *,
        enable_persistence: bool = True,
        backup_count: int = 5,
        auto_save: bool = True,
        enable_plugin_system: bool = True
    ) -> None:
        """
        Initialize TaskManager with optional persistence and plugin system.
        
        Args:
            transcript_store: Audit event store for audit logging
            storage_path: Path for task persistence (defaults to ./task_data)
            enable_persistence: Whether to enable task persistence
            backup_count: Number of backup files to keep
            auto_save: Whether to automatically save after changes
            enable_plugin_system: Whether to enable plugin system for task decomposition
        """
        self.registry = TaskRegistry()
        self.transcript_store = transcript_store

        # Setup plugin system if enabled
        self.plugin_manager = None
        decomposer = None
        if enable_plugin_system:
            self.plugin_manager = TaskPluginManager()
            decomposer = self.plugin_manager.registry.get_decomposition_plugin()
            if not decomposer:
                # Fallback to basic decomposer
                decomposer = TaskDecomposerPlugin()
                logger.warning("Plugin system enabled but no decomposition plugin available, using fallback")
        else:
            # Use basic decomposer
            decomposer = TaskDecomposerPlugin()
        
        # Create task management service
        self.service = TaskManagementService(
            registry=self.registry,
            transcript_store=transcript_store,
            decomposer=decomposer,
            auto_save=auto_save,
            allow_rule_based_test_stub=False
        )
        
        # Create unified service interface
        self.interface = TaskServiceInterface(self.service)
        
        logger.info("TaskManager initialized with database persistence only, plugins=%s", enable_plugin_system)
    
    # === High-level task operations ===
    async def create_mission(self, title: str, content: str, originator_id: str, 
                           strategy: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Create a new mission task with optional decomposition strategy"""
        if self.plugin_manager and strategy:
            # Use plugin-based decomposition
            context = kwargs.get("context", {})
            subtasks = self.plugin_manager.decompose_mission(title, content, strategy, context)
            kwargs["subtasks_preview"] = subtasks
        
        payload = {
            "idempotency_key": f"mission-{title}-{originator_id}",
            "title": title,
            "task_type": TaskType.MISSION,
            "originator_id": originator_id,
            "remarks": content,
            **kwargs
        }
        return await self.service.create_task(payload)
    
    async def create_task(
        self,
        title: str,
        task_type: TaskType,
        originator_id: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        **kwargs
    ) -> ZentexTask:
        """Create a new task"""
        payload = {
            "idempotency_key": f"task-{title}-{originator_id}",
            "title": title,
            "task_type": task_type,
            "originator_id": originator_id,
            "priority": priority,
            **kwargs
        }
        return await self.service.create_task(payload)
    
    def get_task(self, task_id: str) -> Optional[ZentexTask]:
        """Get a task by ID"""
        return self.service.get_task(task_id)
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        tags: Optional[List[str]] = None,
        parent_task_id: Optional[str] = None,
        target_id: Optional[str] = None,
        overdue_only: bool = False,
        source_module: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ZentexTask]:
        """List tasks with optional database-backed filtering and pagination."""
        return self.service.list_tasks(
            status=status,
            priority=priority,
            tags=tags,
            parent_task_id=parent_task_id,
            target_id=target_id,
            overdue_only=overdue_only,
            source_module=source_module,
            metadata_filters=metadata_filters,
            limit=limit,
            offset=offset,
        )
    
    def update_task_status(self, task_id: str, new_status: TaskStatus, remarks: Optional[str] = None) -> ZentexTask:
        """Update task status"""
        return self.service.update_task_status(task_id, new_status, remarks)
    
    def claim_task(self, task_id: str, handler_id: str) -> ZentexTask:
        """Claim a task for execution"""
        return self.service.claim_task(task_id, handler_id)
    
    # === Priority and deadline management ===
    def set_task_priority(self, task_id: str, priority: TaskPriority) -> ZentexTask:
        """Set task priority"""
        task = self.service.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        
        task.priority = priority
        task.last_updated_at = task.last_updated_at  # Trigger update
        return task
    
    def set_task_deadline(self, task_id: str, deadline: Any) -> ZentexTask:
        """Set task deadline"""
        task = self.service.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        
        task.deadline = deadline
        task.last_updated_at = task.last_updated_at  # Trigger update
        return task
    
    def get_overdue_tasks(self) -> List[ZentexTask]:
        """Get all overdue tasks"""
        return self.service.list_tasks(overdue_only=True)
    
    # === Suspension and recovery ===
    def suspend_task(
        self,
        task_id: str,
        reason: str,
        recovery_conditions: Optional[List[str]] = None,
        auto_resume_at: Optional[Any] = None
    ) -> ZentexTask:
        """Suspend a task"""
        return self.service.suspend_task(task_id, reason, recovery_conditions, auto_resume_at)
    
    def resume_task(self, task_id: str, remarks: Optional[str] = None) -> ZentexTask:
        """Resume a suspended task"""
        return self.service.resume_task(task_id, remarks)
    
    def get_suspended_tasks(self, *, limit: int = 100, offset: int = 0) -> List[SuspendedTask]:
        """Get suspended tasks with pagination."""
        return self.service.list_suspended_tasks(limit=limit, offset=offset)
    
    async def check_auto_resume(self) -> List[ZentexTask]:
        """Check and auto-resume tasks"""
        return await self.service.check_auto_resume_tasks()
    
    # === Dependency management ===
    def add_dependency(self, task_id: str, dependency_id: str) -> ZentexTask:
        """Add a dependency to a task"""
        return self.service.add_dependency(task_id, dependency_id)
    
    def remove_dependency(self, task_id: str, dependency_id: str) -> ZentexTask:
        """Remove a dependency from a task"""
        return self.service.remove_dependency(task_id, dependency_id)
    
    def get_dependency_tree(self, task_id: str, max_depth: int = 5) -> Dict[str, Any]:
        """Get dependency tree for a task"""
        return self.service.get_dependency_tree(task_id, max_depth)
    
    def can_execute_task(self, task_id: str) -> Dict[str, Any]:
        """Check if a task can be executed"""
        return self.service.can_execute_task(task_id)
    
    def get_ready_tasks(self) -> List[ZentexTask]:
        """Get tasks that are ready to execute (TODO with satisfied dependencies)"""
        todo_tasks = self.service.list_tasks(status=TaskStatus.TODO)
        ready_tasks = []
        
        for task in todo_tasks:
            can_execute = self.service.can_execute_task(task.task_id)
            if can_execute["can_execute"]:
                ready_tasks.append(task)
        
        return ready_tasks
    
    # === Bulk operations ===
    def bulk_update_status(self, task_ids: List[str], new_status: TaskStatus, remarks: Optional[str] = None) -> Dict[str, Any]:
        """Bulk update task status"""
        return self.service.bulk_update_status(task_ids, new_status, remarks)
    
    def bulk_suspend(self, task_ids: List[str], reason: str, recovery_conditions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Bulk suspend tasks"""
        return self.service.bulk_suspend(task_ids, reason, recovery_conditions)
    
    def bulk_resume(self, task_ids: List[str], remarks: Optional[str] = None) -> Dict[str, Any]:
        """Bulk resume tasks"""
        return self.service.bulk_resume(task_ids, remarks)
    
    def bulk_archive_completed(self, older_than_days: int = 7) -> Dict[str, Any]:
        """Archive completed tasks older than specified days"""
        from datetime import datetime, timezone, timedelta
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        done_tasks = self.service.list_tasks(status=TaskStatus.DONE)
        
        tasks_to_archive = []
        for task in done_tasks:
            if task.completed_at and task.completed_at < cutoff_date:
                tasks_to_archive.append(task.task_id)
        
        if tasks_to_archive:
            return self.bulk_update_status(tasks_to_archive, TaskStatus.ARCHIVED, "Auto-archived old completed task")
        
        return {"success": [], "failed": [], "archived_count": 0}
    
    # === Intervention and control ===
    def intervene_task(
        self,
        task_id: str,
        action: str,
        idempotency_key: str,
        remarks: Optional[str] = None,
        operator_id: str = "web-console-operator"
    ) -> Dict[str, Any]:
        """Apply intervention to a task"""
        return self.service.intervene(task_id, action=action, idempotency_key=idempotency_key, remarks=remarks, operator_id=operator_id)
    
    # === Plugin system operations ===
    def get_available_decomposition_strategies(self) -> List[str]:
        """Get available task decomposition strategies"""
        if not self.plugin_manager:
            return []
        return self.plugin_manager.get_available_strategies()
    
    def get_plugin_info(self, plugin_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get plugin information"""
        if not self.plugin_manager:
            return None
        return self.plugin_manager.get_plugin_info(plugin_id)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins"""
        if not self.plugin_manager:
            return []
        return self.plugin_manager.list_plugins()
    
    def set_default_decomposition_strategy(self, strategy: str) -> bool:
        """Set default decomposition strategy"""
        if not self.plugin_manager:
            return False
        return self.plugin_manager.set_default_strategy(strategy)
    
    def decompose_mission_with_strategy(self, title: str, content: str, 
                                      strategy: Optional[str] = None, 
                                      context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Decompose mission using specific strategy"""
        if not self.plugin_manager:
            return []
        return self.plugin_manager.decompose_mission(title, content, strategy, context)
    
    # === Statistics and monitoring ===
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get task statistics using aggregate service queries."""
        service_stats = self.service.get_task_statistics()
        return {
            "total_tasks": service_stats.get("total_tasks", 0),
            "by_status": service_stats.get("tasks_by_status", {}),
            "by_priority": service_stats.get("tasks_by_priority", {}),
            "overdue_count": service_stats.get("overdue_count", 0),
            "suspended_count": service_stats.get("suspended_tasks", 0),
            "ready_to_execute": service_stats.get("active_tasks", 0),
        }
    
    def get_persistence_stats(self) -> Optional[Dict[str, Any]]:
        """Get persistence statistics"""
        return self.service.get_persistence_stats()
    
    def get_plugin_stats(self) -> Optional[Dict[str, Any]]:
        """Get plugin system statistics"""
        if not self.plugin_manager:
            return None
        return self.plugin_manager.get_registry_stats()
    
    def save_state(self) -> bool:
        """Manually save current state"""
        return self.service.save_state()
    
    # === Cleanup ===
    def cleanup_failed_tasks(self, force: bool = False) -> Dict[str, Any]:
        """Clean up failed tasks"""
        failed_tasks = self.service.list_tasks(status=TaskStatus.FAILED)
        task_ids = [task.task_id for task in failed_tasks]
        
        if task_ids:
            return self.service.bulk_delete(task_ids, force=force)
        
        return {"success": [], "failed": [], "deleted_count": 0}
    
    # === Unified interface access ===
    def get_service_interface(self) -> TaskServiceInterface:
        """Get the unified service interface for external modules"""
        return self.interface
