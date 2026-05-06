from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceWorkerTimeoutMixin:
    async def run_worker_cycle(self) -> Dict[str, Any]:
        """
        Execute one worker heartbeat cycle.
        Pulls TODO tasks, routes them, and executes them via plugins.
        """
        if not self._task_dao:
            logger.warning("run_worker_cycle invoked but database/DAO is unavailable.")
            return {"tasks_dispatched": 0}

        logger.info("TaskManagementService: Starting worker heartbeat cycle...")
        try:
            stats = await self._dispatch_manager.run_cycle(self._task_dao)
            return stats.__dict__ if hasattr(stats, "__dict__") else {}
        except Exception as e:
            logger.exception("Worker heartbeat cycle failed at service level: %s", e)
            return {"error": str(e)}

    async def check_auto_resume_tasks(self) -> List[ZentexTask]:
        """Check and auto-resume tasks whose auto_resume_at time has arrived.
        Also reclaims stale IN_PROGRESS tasks (G39).
        """
        if not self._auto_resume_leader.try_acquire():
            return [] # Only the leader node performs auto-resume and reclamation

        now = datetime.now(timezone.utc)
        processed_tasks = []
        
        # 1. Auto-resume suspended tasks
        all_suspensions = self._shared_suspensions.list_all(SuspendedTask)
        for task_id, suspension_info in all_suspensions.items():
            if suspension_info.auto_resume_at and suspension_info.auto_resume_at <= now:
                try:
                    resumed_task = await self.resume_task(task_id, "Auto-resumed by system leader")
                    processed_tasks.append(resumed_task)
                    logger.info(f"Auto-resumed task {task_id}")
                except Exception as e:
                    # Forbidden: auto-resume failures must leave a traceback.
                    # Logging a plain error string here hides the real root cause
                    # and makes the scheduler look healthier than it is.
                    logger.exception("Failed to auto-resume task %s: %s", task_id, e)

        # 1b. G9 resource-gap recovery: if the missing executor has become
        # query-visible and healthy, resume the assignment_pending subtask and
        # route it through the normal G31A assignment gate.
        assignment_router = self._build_assignment_router()
        for suspension_info in self.list_suspended_tasks(limit=500, offset=0):
            try:
                decision = await assignment_router.try_resume_suspended_assignment(self, suspension_info)
                if decision is None or not decision.assigned:
                    continue
                resumed = self.get_task(suspension_info.task_id)
                if resumed is not None:
                    processed_tasks.append(resumed)
                    logger.info(
                        "G9 auto-resumed resource-gap task %s with owner %s.",
                        suspension_info.task_id,
                        decision.owner_ref,
                    )
            except Exception as e:
                logger.exception("Failed to G9-auto-resume task %s: %s", suspension_info.task_id, e)
        
        # 2. Reclaim stale IN_PROGRESS tasks (G39) in bounded database pages.
        in_progress_tasks: List[ZentexTask] = []
        offset = 0
        page_size = 500
        while True:
            page = self.list_tasks(status=TaskStatus.IN_PROGRESS, limit=page_size, offset=offset)
            in_progress_tasks.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        stale_threshold = 300 # Default 5 minutes
        
        for task in in_progress_tasks:
            # 1. Determine the effective stale threshold for this specific task
            # Priority: task metadata > service default (300s)
            stale_threshold = task.metadata.get("stale_timeout", 300)
            
            # Check last_updated_at instead of started_at to allow heartbeats
            elapsed = (now - task.last_updated_at).total_seconds()
            if elapsed > stale_threshold:
                try:
                    if task.contract.retriable:
                        logger.warning(f"Reclaiming stale task {task.task_id} (threshold={stale_threshold}s): resetting to TODO.")
                        await self.update_task_status(
                            task.task_id, 
                            TaskStatus.TODO, 
                            remarks=f"Reclaimed from stale IN_PROGRESS state after {elapsed:.0f}s (Threshold: {stale_threshold}s)."
                        )
                        await self.update_task_metadata(
                            task.task_id,
                            {
                                "orphan_recovery": {
                                    "orphan_detected": True,
                                    "detector": "G39.stale_in_progress_orphan_detector",
                                    "from_status": TaskStatus.IN_PROGRESS.value,
                                    "to_status": TaskStatus.TODO.value,
                                    "elapsed_seconds": round(elapsed, 3),
                                    "stale_threshold_seconds": stale_threshold,
                                    "resources_reclaimed": True,
                                    "reassign": {
                                        "strategy": "failed_reassign_to_dispatch_queue",
                                        "target_status": TaskStatus.TODO.value,
                                    },
                                    "previous_lease": task.metadata.get("lease") if isinstance(task.metadata, dict) else None,
                                }
                            },
                            remarks="Orphan detector reclaimed stale IN_PROGRESS task and queued reassignment",
                        )
                    else:
                        logger.error(f"Reclaiming stale task {task.task_id} (threshold={stale_threshold}s): non-retriable, marking FAILED.")
                        await self.update_task_status(
                            task.task_id, 
                            TaskStatus.FAILED, 
                            remarks=f"Reclaimed from stale IN_PROGRESS state after {elapsed:.0f}s (Non-retriable, Threshold: {stale_threshold}s)."
                        )
                        await self.update_task_metadata(
                            task.task_id,
                            {
                                "orphan_recovery": {
                                    "orphan_detected": True,
                                    "detector": "G39.stale_in_progress_orphan_detector",
                                    "from_status": TaskStatus.IN_PROGRESS.value,
                                    "to_status": TaskStatus.FAILED.value,
                                    "elapsed_seconds": round(elapsed, 3),
                                    "stale_threshold_seconds": stale_threshold,
                                    "resources_reclaimed": True,
                                    "reassign": {
                                        "strategy": "non_retriable_failed_no_reassign",
                                        "target_status": TaskStatus.FAILED.value,
                                    },
                                    "previous_lease": task.metadata.get("lease") if isinstance(task.metadata, dict) else None,
                                }
                            },
                            remarks="Orphan detector reclaimed stale non-retriable task and failed it",
                        )
                    processed_tasks.append(task)
                except Exception as e:
                    logger.exception("Failed to reclaim stale task %s: %s", task.task_id, e)
        
        return processed_tasks

    async def check_timeout_and_republish_tasks(
        self,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Reclaim timed-out IN_PROGRESS tasks and republish retriable work.

        Forbidden behavior:
        - exposing a timeout recovery entry point but leaving it as a fake stub
        - swallowing lease parsing or recovery failures and pretending the scheduler is healthy
        Both behaviors hide real stuck-task faults and directly damage runtime stability.
        """
        now = datetime.now(timezone.utc)
        recovered: List[Dict[str, Any]] = []
        in_progress_tasks = self.list_tasks(
            status=TaskStatus.IN_PROGRESS,
            limit=max(1, min(int(limit), 500)) if limit is not None else 100,
            offset=0,
        )

        for task in in_progress_tasks:
            try:
                action = build_timeout_recovery_action(task, now=now)
                if action is None:
                    continue

                original_metadata = copy.deepcopy(task.metadata)

                try:
                    await self.update_task_metadata(task.task_id, action.metadata)
                    await self.update_task_status(
                        task.task_id,
                        action.new_status,
                        remarks=action.remarks,
                    )
                    if action.last_error is not None:
                        if not self._task_dao:
                            raise RuntimeError("Task DAO is unavailable")
                        extra_updates = {
                            "last_error": action.last_error[:2000],
                            "execution_finished_at": action.execution_finished_at,
                        }
                        if not self._task_dao.update_task(task.task_id, extra_updates):
                            raise TaskStateError(
                                f"Failed to persist timeout recovery fault for task {task.task_id}"
                            )
                except Exception:
                    current_task = self.get_task(task.task_id) or task
                    current_task.metadata = original_metadata
                    self._shared_tasks.set(task.task_id, current_task)
                    self._tasks[task.task_id] = current_task
                    if self.use_database:
                        self._sync_task_to_database(current_task)
                    raise

                logger.warning(
                    "Recovered in_progress task %s to %s during timeout recovery.",
                    task.task_id,
                    action.new_status.value,
                )
                recovered.append(action.result)
            except Exception as exc:
                # Forbidden: silently skipping broken lease state would make the scheduler
                # look healthy while timed-out tasks remain stuck forever.
                logger.exception(
                    "Task timeout recovery failed for %s: %s",
                    task.task_id,
                    exc,
                )

        return recovered


