from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceStatusControlMixin:
    async def claim_task(self, task_id: str, handler_id: str) -> ZentexTask:
        """
        Collaborative claiming of a subtask.
        """
        task = self.get_task(task_id)
        if not task:
             raise KeyError(f"Task {task_id} not found")
             
        # Check dependencies
        for dep_id in task.depends_on:
            dep_task = self.get_task(dep_id)
            if dep_task and dep_task.status != TaskStatus.DONE:
                raise TaskStateError(f"Dependency {dep_id} is not yet DONE.")

        task.target_id = handler_id
        task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if self.use_database and not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist task claim target for {task_id}")
        return await self.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks=f"Claimed by {handler_id}")

    async def heartbeat_task(self, task_id: str) -> None:
        """
        G39: Signal that a task is still active. 
        Updates last_updated_at to prevent stale reclamation.
        """
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"Heartbeat attempted for non-existent task: {task_id}")
            return

        now = datetime.now(timezone.utc)
        task.last_updated_at = now
        
        # Save to shared and local memory
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task

        # Save to database (only update the timestamp to minimize overhead)
        if self.use_database and self._task_dao:
            try:
                if not self._task_dao.update_task(task_id, {"last_updated_at": now.isoformat()}):
                    raise TaskStateError(f"Failed to persist task heartbeat for {task_id}")
            except Exception as e:
                logger.error(f"Failed to persist task heartbeat for {task_id}: {e}")
                raise

        # Record minor audit event
        self._record_audit(task_id, "TASK_HEARTBEAT", {"timestamp": now.isoformat()})

    async def update_task_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        remarks: Optional[str] = None,
        *,
        skip_verification_bridge: bool = False,
    ):
        """
        State Machine Redline: Validates illegal transitions.
        
        G16: Atomic status update.
        G18: Asynchronous execution.
        """
        if isinstance(new_status, str):
            new_status = TaskStatus(new_status)
        task = self.get_task(task_id)  # Returns most current state from DB/Shared
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if not skip_verification_bridge:
            bridged_task = await maybe_route_done_status_update_through_verification(
                self,
                task=task,
                task_id=task_id,
                new_status=new_status,
                remarks=remarks,
            )
            if bridged_task is not None:
                return bridged_task

        # Define legal transitions
        legal_from: Dict[TaskStatus, List[TaskStatus]] = {
            TaskStatus.SPLIT_REQUIRED: [TaskStatus.ASSIGNMENT_PENDING, TaskStatus.DONE, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELLED],
            TaskStatus.ASSIGNMENT_PENDING: [TaskStatus.QUEUED, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.CANCELLED],
            TaskStatus.QUEUED: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED, TaskStatus.CANCELLED],
            TaskStatus.TODO: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED, TaskStatus.CANCELLED],
            TaskStatus.IN_PROGRESS: [TaskStatus.TODO, TaskStatus.WAITING_CONFIRMATION, TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED, TaskStatus.CANCELLED],
            TaskStatus.BLOCKED: [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED, TaskStatus.CANCELLED],
            TaskStatus.WAITING_CONFIRMATION: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED, TaskStatus.CANCELLED],
            TaskStatus.SUSPENDED: [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.ARCHIVED, TaskStatus.CANCELLED],
            TaskStatus.DONE: [TaskStatus.ARCHIVED], # Can only archive done tasks
            TaskStatus.FAILED: [TaskStatus.TODO, TaskStatus.ARCHIVED], # Allow retry or archive
            TaskStatus.ARCHIVED: [], # Terminal state
            TaskStatus.CANCELLED: [], # Terminal state
        }
        
        if new_status not in legal_from.get(task.status, []):
            raise TaskStateError(f"Illegal transition: {task.status} -> {new_status}")

        old_status = task.status
        
        # Update metadata and timestamps
        task.update_status(new_status, remarks)
        
        # Save to shared state
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        
        # Save to database if enabled
        if self.use_database:
            if not self._sync_task_to_database(task):
                # Rollback in-memory state to prevent desync
                task.status = old_status
                self._shared_tasks.set(task_id, task)
                self._tasks[task_id] = task
                logger.error(f"Failed to persist task {task_id} status change ({old_status} -> {new_status}) to database. Rolled back in-memory state.")
                raise TaskStateError(f"Persistence failure for task {task_id}. Database synchronization failed.")
            
            # Log audit to database
            if self._audit_dao:
                try:
                    self._audit_dao.log_action(
                        task_id=task_id,
                        action="TASK_STATUS_UPDATED",
                        operator_id="system",
                        old_status=old_status.value,
                        new_status=new_status.value,
                        details={"remarks": remarks}
                    )
                except Exception as audit_err:
                     logger.error(f"Failed to log task audit: {audit_err}")
                     raise
        
        # Record audit to transcript (legacy)
        self._record_audit(task_id, "TASK_STATUS_UPDATED", {"new_status": new_status, "remarks": remarks})

        return task

    def delete_task(self, task_id: str, *, force: bool = False) -> bool:
        """Delete a task through the official service boundary."""
        task = self.get_task(task_id)
        if task is None:
            return False
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")

        deleted = self._task_dao.delete_task(task_id, force=force)
        if not deleted:
            return False
        if self._audit_dao:
            self._audit_dao.log_action(
                task_id=task_id,
                action="TASK_DELETED",
                operator_id="system",
                old_status=task.status.value,
                new_status="deleted",
                details={
                    "force": force,
                    "title": task.title,
                    "remarks": "任务已从任务管理中心删除",
                },
            )

        self._shared_tasks.delete(task_id)
        self._tasks.pop(task_id, None)
        if task.idempotency_key:
            self._shared_idempotency.delete(task.idempotency_key)
            self._idempotency_log.pop(task.idempotency_key, None)
            if self._idempotency_dao:
                self._idempotency_dao.delete(task.idempotency_key)

        self._record_audit(task_id, "TASK_DELETED", {"force": force})
        return True

    async def intervene(
        self,
        task_id: str,
        *,
        action: str,
        idempotency_key: str,
        remarks: Optional[str] = None,
        operator_id: str = "web-console-operator",
    ) -> Dict[str, Any]:
        """
        Apply an operator intervention with strict idempotency.

        Redlines:
        - every intervention MUST carry an idempotency_key
        - repeated calls with the same key must be replay-safe
        - intervention must be auditable in transcript_store
        """
        if not idempotency_key or not str(idempotency_key).strip():
            raise ValueError("idempotency_key is required")

        cached = self._intervention_receipts.get(idempotency_key)
        if cached is not None:
            return {**cached, "idempotent_replay": True}

        status_map = {
            "pause": TaskStatus.BLOCKED,
            "retry": TaskStatus.TODO,
            "resume": TaskStatus.IN_PROGRESS,
            "approve": TaskStatus.DONE,
            "reject": TaskStatus.FAILED,
            "take_over": TaskStatus.IN_PROGRESS,
            "suspend": TaskStatus.SUSPENDED,
            "archive": TaskStatus.ARCHIVED,
            "cancel": TaskStatus.CANCELLED,
            "cancelled": TaskStatus.CANCELLED,
        }
        new_status = status_map.get(action)
        if new_status is None:
            raise ValueError("Invalid intervention action")

        recorded_at = datetime.now(timezone.utc).isoformat()
        updated = await self.update_task_status(task_id, new_status, remarks=remarks)
        receipt = {
            "idempotency_key": idempotency_key,
            "task_id": task_id,
            "action": action,
            "new_status": updated.status.value,
            "remarks": remarks,
            "operator_id": operator_id,
            "recorded_at": recorded_at,
        }
        updated = await self.update_task_metadata(
            task_id,
            {
                "last_intervention": receipt,
                "intervention_history": [
                    *(
                        updated.metadata.get("intervention_history", [])
                        if isinstance(updated.metadata.get("intervention_history"), list)
                        else []
                    ),
                    receipt,
                ],
            },
            remarks=remarks or f"Operator intervention recorded: {action}",
        )
        self._intervention_receipts[idempotency_key] = receipt
        if self._intervention_dao:
            self._intervention_dao.record_intervention(receipt)
        self._record_audit(
            task_id,
            "TASK_INTERVENED",
            {
                "idempotency_key": idempotency_key,
                "action": action,
                "new_status": updated.status.value,
                "remarks": remarks,
                "operator_id": operator_id,
            },
        )
        return {**receipt, "idempotent_replay": False}


