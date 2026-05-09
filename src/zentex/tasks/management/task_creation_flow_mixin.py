from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceCreationFlowMixin:
    async def create_task(self, payload: Dict[str, Any]) -> ZentexTask:
        """Create a new task with database persistence and noise-policy gating."""
        payload = dict(payload)
        force_execute = self._truthy(payload.pop("force_execute", False))
        enable_llm_semantic_scoring = self._truthy(payload.pop("enable_llm_semantic_scoring", False))
        skip_noise_analysis = self._truthy(payload.pop("skip_noise_analysis", False))
        payload["task_scope"] = self._derive_task_scope(payload)
        payload["execution_assignment"] = self._derive_execution_assignment(payload)
        task_id = str(uuid4())[:8]
        original_idempotency_key = str(payload.get("idempotency_key") or "")
        noise_analysis_report: Dict[str, Any] | None = None
        auto_cancelled_by_policy = False

        if original_idempotency_key:
            existing_task = self._get_task_for_idempotency_key(original_idempotency_key)
            if existing_task is not None:
                logger.warning(
                    "Absolute idempotency collision blocked before semantic/noise policy. idempotency_key=%s task_id=%s",
                    original_idempotency_key,
                    existing_task.task_id,
                )
                return existing_task

        if not skip_noise_analysis:
            candidate_payload = copy.deepcopy(payload)
            candidate_payload.setdefault("status", TaskStatus.TODO.value)
            candidate = ZentexTask(task_id=task_id, **candidate_payload)
            noise_analysis_report = build_task_creation_analysis_report(
                existing_tasks=self._list_tasks_for_internal_scan(),
                candidate_task=candidate,
                force_execute=force_execute,
                enable_llm_semantic_scoring=enable_llm_semantic_scoring,
                workspace_environment_context=self._task_noise_workspace_context(payload),
            )
            analysis = noise_analysis_report["TaskAnalysisReport"]
            policy_would_reject = analysis.get("decision") in {"rejected", "merge_and_drop", "force_allowed"}
            if policy_would_reject and not force_execute:
                auto_cancelled_by_policy = True
                payload["status"] = TaskStatus.CANCELLED.value
                payload["completed_at"] = datetime.now(timezone.utc)
                payload["idempotency_key"] = f"auto-cancelled:{original_idempotency_key or 'no-key'}:{task_id}"
            elif policy_would_reject and force_execute:
                payload["idempotency_key"] = f"force-execute:{original_idempotency_key or 'no-key'}:{task_id}"

            metadata = dict(payload.get("metadata") or {})
            metadata["task_noise_analysis_report"] = noise_analysis_report
            metadata["task_noise_decision"] = "auto_cancelled" if auto_cancelled_by_policy else analysis.get("decision")
            metadata["task_noise_force_execute"] = force_execute
            if original_idempotency_key and payload.get("idempotency_key") != original_idempotency_key:
                metadata["original_idempotency_key"] = original_idempotency_key
            if auto_cancelled_by_policy:
                metadata["auto_cancel_reason"] = analysis.get("rejection_reason")
                metadata["cancelled_by_policy"] = True
                metadata["policy_cancel_status"] = "cancelled_by_policy/conflict"
                if analysis.get("decision") == "merge_and_drop":
                    metadata["semantic_duplicate_merge"] = {
                        "merged_by_policy": True,
                        "resource_allocation": "skipped",
                        "target_merge_task_id": analysis.get("target_merge_task_id"),
                        "reused_execution_receipt": self._build_task_execution_receipt(
                            analysis.get("target_merge_task_id")
                        ),
                    }
                if analysis.get("decision") == "rejected":
                    scores = analysis.get("scores") if isinstance(analysis.get("scores"), dict) else {}
                    metadata["semantic_policy_cancel"] = {
                        "cancelled_by_policy": True,
                        "conflict_status": "cancelled_by_policy/conflict",
                        "duplicate_score": scores.get("duplicate_score"),
                        "junk_score": scores.get("junk_score"),
                        "llm_semantic_evaluation": analysis.get("llm_semantic_evaluation"),
                    }
            if force_execute and policy_would_reject:
                metadata["force_execute_reason"] = (
                    f"Policy would cancel this task, but force_execute=true overrode the decision: "
                    f"{analysis.get('rejection_reason')}"
                )
            payload["metadata"] = metadata

        # Check idempotency (Shared)
        key = payload.get("idempotency_key")
        if key:
            # Check database first if enabled
            if self.use_database and self._idempotency_dao:
                existing_task_id = self._idempotency_dao.check_idempotency(key)
                if existing_task_id:
                    logger.warning(f"Duplicate task submission with idempotency_key: {key}")
                    existing_task = self.get_task(existing_task_id)
                    if existing_task:
                        return existing_task
                    logger.warning(
                        "Stale database idempotency entry points to missing task; clearing and creating a new task. "
                        "idempotency_key=%s task_id=%s",
                        key,
                        existing_task_id,
                    )
                    self._idempotency_dao.delete(key)
            
            # Fallback to shared state
            existing_id = self._shared_idempotency.get(key)
            if existing_id:
                logger.warning(f"Duplicate task submission with idempotency_key: {key}")
                existing_task = self.get_task(existing_id)
                if existing_task is not None:
                    return existing_task
                logger.warning(
                    "Stale shared idempotency entry points to missing task; clearing and creating a new task. "
                    "idempotency_key=%s task_id=%s",
                    key,
                    existing_id,
                )
                self._shared_idempotency.delete(key)

        # Distributed lock to prevent race during creation
        lock_id = key if key else f"new-task-{uuid4()}"
        with get_lock_for_resource(f"task-create:{lock_id}"):
            # Re-check idempotency inside lock
            if key:
                if self.use_database and self._idempotency_dao:
                    existing_task_id = self._idempotency_dao.check_idempotency(key)
                    if existing_task_id:
                        existing_task = self.get_task(existing_task_id)
                        if existing_task is not None:
                            return existing_task
                        logger.warning(
                            "Stale database idempotency entry found inside create lock; clearing and creating a new task. "
                            "idempotency_key=%s task_id=%s",
                            key,
                            existing_task_id,
                        )
                        self._idempotency_dao.delete(key)
                
                existing_id = self._shared_idempotency.get(key)
                if existing_id:
                    existing_task = self.get_task(existing_id)
                    if existing_task is not None:
                        return existing_task
                    logger.warning(
                        "Stale shared idempotency entry found inside create lock; clearing and creating a new task. "
                        "idempotency_key=%s task_id=%s",
                        key,
                        existing_id,
                    )
                    self._shared_idempotency.delete(key)

            task = ZentexTask(
                task_id=task_id,
                **payload
            )
            
            # Save to shared state
            self._shared_tasks.set(task_id, task)
            self._tasks[task_id] = task
            
            # Save to database if enabled
            if not self._sync_task_to_database(task):
                self._shared_tasks.delete(task_id)
                self._tasks.pop(task_id, None)
                raise TaskStateError(f"Failed to persist task {task_id} to database")
            if key and self._idempotency_dao:
                self._idempotency_dao.record_idempotency(key, task_id)
            
            # Legacy: save to shared idempotency
            if key:
                self._shared_idempotency.set(key, task_id)

            # Record audit
            self._record_audit(task_id, "TASK_CREATED", {"payload": payload})
            if auto_cancelled_by_policy:
                self._record_audit(
                    task_id,
                    "TASK_NOISE_AUTO_CANCELLED",
                    {
                        "original_idempotency_key": original_idempotency_key,
                        "analysis_report": noise_analysis_report,
                    },
                )
                writeback = self._write_task_noise_signal_to_memory_reflection_learning(
                    task,
                    analysis_report=noise_analysis_report,
                    original_idempotency_key=original_idempotency_key,
                )
                task.metadata["task_noise_experience_writeback"] = writeback
                self._shared_tasks.set(task_id, task)
                self._tasks[task_id] = task
                if self.use_database and not self._sync_task_to_database(task):
                    raise TaskStateError(f"Failed to persist task noise writeback metadata for task {task_id}")
            elif force_execute and noise_analysis_report and noise_analysis_report["TaskAnalysisReport"].get("decision") == "force_allowed":
                self._record_audit(
                    task_id,
                    "TASK_NOISE_FORCE_EXECUTED",
                    {
                        "original_idempotency_key": original_idempotency_key,
                        "analysis_report": noise_analysis_report,
                    },
                )
            
            # Auto-decompose missions
            if task.task_type == TaskType.MISSION and task.status != TaskStatus.CANCELLED:
                asyncio.create_task(self.decompose_and_dispatch_mission(task))
                
            return self._attach_validated_execution_assignment(task)

    def _get_task_for_idempotency_key(self, key: str) -> Optional[ZentexTask]:
        if not key:
            return None
        if self.use_database and self._idempotency_dao:
            existing_task_id = self._idempotency_dao.check_idempotency(key)
            if existing_task_id:
                existing_task = self.get_task(existing_task_id)
                if existing_task is not None:
                    return existing_task
                logger.warning(
                    "Stale database idempotency entry points to missing task; clearing. idempotency_key=%s task_id=%s",
                    key,
                    existing_task_id,
                )
                self._idempotency_dao.delete(key)
        existing_id = self._shared_idempotency.get(key)
        if existing_id:
            existing_task = self.get_task(existing_id)
            if existing_task is not None:
                return existing_task
            logger.warning(
                "Stale shared idempotency entry points to missing task; clearing. idempotency_key=%s task_id=%s",
                key,
                existing_id,
            )
            self._shared_idempotency.delete(key)
        return None

    def _build_task_execution_receipt(self, task_id: Any) -> Dict[str, Any]:
        if not task_id:
            return {"status": "missing_source_task", "task_id": None}
        source = self.get_task(str(task_id))
        if source is None:
            return {"status": "missing_source_task", "task_id": str(task_id)}
        outcome: Optional[Dict[str, Any]] = None
        try:
            outcome = self.get_task_outcome(source.task_id) if self._outcome_dao else None
        except Exception as exc:
            outcome = {"status": "outcome_lookup_failed", "error": f"{type(exc).__name__}: {exc}"}
        return {
            "status": "reused_source_task_receipt",
            "task_id": source.task_id,
            "task_status": source.status.value if isinstance(source.status, TaskStatus) else str(source.status),
            "dispatch_plugin_id": source.dispatch_plugin_id,
            "execution_started_at": source.execution_started_at,
            "execution_finished_at": source.execution_finished_at,
            "execution_output": source.execution_output,
            "task_outcome": outcome,
        }


