from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceSuspensionMixin:
    async def suspend_task(self, 
                    task_id: str, 
                    reason: str,
                    recovery_conditions: Optional[List[str]] = None,
                    auto_resume_at: Optional[datetime] = None,
                    suspension_context: Optional[Dict[str, Any]] = None) -> ZentexTask:
        """Suspend a task with recovery context"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if task.status not in [TaskStatus.ASSIGNMENT_PENDING, TaskStatus.QUEUED, TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]:
            raise TaskStateError(f"Cannot suspend task in status: {task.status}")
            
        original_status = task.status
        task.update_status(TaskStatus.SUSPENDED, remarks=f"Suspended: {reason}")
        
        # Create suspension record (Shared)
        suspended_task = SuspendedTask(
            task_id=task_id,
            original_status=original_status,
            suspension_reason=reason,
            recovery_conditions=recovery_conditions or [],
            suspension_context=suspension_context or {},
            auto_resume_at=auto_resume_at
        )
        
        self._shared_suspensions.set(task_id, suspended_task)
        self._shared_tasks.set(task_id, task) # Update task status in shared store
        self._tasks[task_id] = task
        if not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist suspended task {task_id}")
        if self._suspended_dao:
            self._suspended_dao.suspend_task(
                {
                    "task_id": task_id,
                    "original_status": original_status.value,
                    "suspension_reason": reason,
                    "recovery_conditions": recovery_conditions or [],
                    "suspension_context": suspension_context or {},
                    "suspended_at": suspended_task.suspended_at.isoformat(),
                    "auto_resume_at": auto_resume_at.isoformat() if auto_resume_at else None,
                }
            )
        
        self._record_audit(task_id, "TASK_SUSPENDED", {
            "reason": reason,
            "recovery_conditions": recovery_conditions,
            "auto_resume_at": auto_resume_at.isoformat() if auto_resume_at else None
        })
        
        return task

    async def resume_task(self, task_id: str, remarks: Optional[str] = None) -> ZentexTask:
        """Resume a suspended task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if task.status != TaskStatus.SUSPENDED:
            raise TaskStateError(f"Task {task_id} is not suspended")
            
        suspension_info = self.get_suspended_task(task_id)
        if not suspension_info:
            raise KeyError(f"No suspension info found for task {task_id}")
            
        # Restore original status
        task.update_status(suspension_info.original_status, 
                          remarks=remarks or f"Resumed from suspension: {suspension_info.suspension_reason}")
        
        # Clean up suspension record
        self._shared_suspensions.delete(task_id)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist resumed task {task_id}")
        if self._suspended_dao:
            self._suspended_dao.resume_task(task_id)
        
        self._record_audit(task_id, "TASK_RESUMED", {
            "original_status": suspension_info.original_status.value,
            "suspension_reason": suspension_info.suspension_reason,
            "remarks": remarks
        })
        
        return task

    def get_suspended_task(self, task_id: str) -> Optional[SuspendedTask]:
        """Get suspension information for a task"""
        if self._suspended_dao:
            payload = self._suspended_dao.get_suspended_task(task_id)
            if payload:
                return SuspendedTask.model_validate(payload)
        return self._shared_suspensions.get(task_id, SuspendedTask)

    def list_suspended_tasks(
        self,
        *,
        task_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SuspendedTask]:
        """List suspended tasks with database-backed filtering and pagination."""
        if self._suspended_dao:
            return [
                SuspendedTask.model_validate(item)
                for item in self._suspended_dao.list_suspended_tasks(
                    task_id=task_id,
                    limit=limit,
                    offset=offset,
                )
            ]
        all_suspensions = self._shared_suspensions.list_all(SuspendedTask)
        suspensions = list(all_suspensions.values())
        if task_id:
            suspensions = [item for item in suspensions if item.task_id == task_id]
        return suspensions[max(0, int(offset)): max(0, int(offset)) + max(1, min(int(limit), 500))]

    def trigger_negotiation_scans(self) -> List[Any]:
        """
        Scan all current suspended tasks and generate negotiation requests.
        """
        suspended = self._list_suspended_tasks_for_internal_scan()
        new_negs = self.negotiation_generator.scan_for_gaps(suspended)
        
        for neg in new_negs:
             self._record_audit(
                 neg.target_task_id, 
                 "NEGOTIATION_GENERATED", 
                 {"negotiation_id": neg.negotiation_id, "gap": neg.gap_type}
             )
             
        return new_negs


