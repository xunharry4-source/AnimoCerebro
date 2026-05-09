from __future__ import annotations

"""Task service interface contracts only.

Concrete task lifecycle, persistence, decomposition, assignment, verification,
and plugin helper implementations must live in the domain subpackages under
``zentex.tasks``.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from zentex.tasks.models import SuspendedTask, TaskPriority, TaskStatus, TaskType, ZentexTask


@runtime_checkable
class TaskManagementServiceInterface(Protocol):
    """Public task-management service contract."""

    async def create_task(self, payload: Dict[str, Any]) -> ZentexTask:
        ...

    def get_task(self, task_id: str) -> Optional[ZentexTask]:
        ...

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
        ...

    async def update_task_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        remarks: Optional[str] = None,
    ) -> ZentexTask:
        ...

    async def claim_task(self, task_id: str, handler_id: str) -> ZentexTask:
        ...

    async def suspend_task(
        self,
        task_id: str,
        reason: str,
        recovery_conditions: Optional[List[str]] = None,
        auto_resume_at: Optional[Any] = None,
    ) -> ZentexTask:
        ...

    async def resume_task(self, task_id: str, remarks: Optional[str] = None) -> ZentexTask:
        ...

    def list_suspended_tasks(self, *, limit: int = 100, offset: int = 0) -> List[SuspendedTask]:
        ...

    async def check_auto_resume_tasks(self) -> List[ZentexTask]:
        ...

    async def complete_task_with_verification(
        self,
        task_id: str,
        result: Any = None,
        remarks: Optional[str] = None,
        **kwargs: Any,
    ) -> ZentexTask:
        ...


__all__ = ["TaskManagementServiceInterface"]
