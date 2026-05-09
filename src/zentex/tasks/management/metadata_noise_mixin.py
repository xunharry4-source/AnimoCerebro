from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceMetadataNoiseMixin:
    async def update_task_metadata(
        self,
        task_id: str,
        metadata_updates: Dict[str, Any],
        *,
        remarks: Optional[str] = None,
    ) -> ZentexTask:
        """Merge metadata into a task and persist the change."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        task.metadata = {**task.metadata, **metadata_updates}
        task.last_updated_at = datetime.now(timezone.utc)
        if remarks:
            task.remarks = remarks

        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task

        if self.use_database:
            if not self._sync_task_to_database(task):
                raise TaskStateError(f"Failed to persist metadata updates for task {task_id}")
            if self._audit_dao:
                self._audit_dao.log_action(
                    task_id=task_id,
                    action="TASK_METADATA_UPDATED",
                    operator_id="system",
                    old_status=task.status.value,
                    new_status=task.status.value,
                    details={"metadata_updates": metadata_updates, "remarks": remarks},
                )

        self._record_audit(
            task_id,
            "TASK_METADATA_UPDATED",
            {"metadata_updates": metadata_updates, "remarks": remarks},
        )
        # Read-after-write guard: metadata mutation must be query-visible.
        refreshed = self._load_task_from_database(task_id)
        if refreshed is None or any(
            refreshed.metadata.get(key) != value for key, value in metadata_updates.items()
        ):
            raise TaskStateError(f"Metadata read-after-write mismatch for task {task_id}")
        return task

    def _write_task_noise_signal_to_memory_reflection_learning(
        self,
        task: ZentexTask,
        *,
        analysis_report: Dict[str, Any] | None,
        original_idempotency_key: str,
    ) -> Dict[str, Any]:
        report = (analysis_report or {}).get("TaskAnalysisReport", {})
        trace_id = str(task.metadata.get("trace_id") or f"task-noise:{task.task_id}")
        source_module = str(task.metadata.get("source_module") or task.metadata.get("source") or task.originator_id or "unknown")
        rejection_reason = str(report.get("rejection_reason") or task.metadata.get("auto_cancel_reason") or "")
        root_cause = (
            f"Task was automatically cancelled as duplicate/noise. Originator={task.originator_id}; "
            f"source_module={source_module}; original_idempotency_key={original_idempotency_key or 'missing'}; "
            f"decision={report.get('decision')}; scores={report.get('scores')}; reason={rejection_reason}"
        )
        actionable_adjustment = (
            "Upstream generators should reuse stable idempotency keys, check active/recent task intent before creating new work, "
            "attach concrete workspace evidence, and stop generating follow-up tasks when the target objective is already covered."
        )
        payload = {
            "source": "task_noise_auto_cancel",
            "task_id": task.task_id,
            "task_title": task.title,
            "task_status": task.status.value,
            "originator_id": task.originator_id,
            "source_module": source_module,
            "target_id": task.target_id,
            "original_idempotency_key": original_idempotency_key,
            "effective_idempotency_key": task.idempotency_key,
            "analysis_report": analysis_report,
            "root_cause": root_cause,
            "actionable_adjustment": actionable_adjustment,
            "avoid_pattern": "Do not emit semantically duplicate or low-evidence tasks after a task center cancellation receipt.",
            "recommended_next_action": "Inspect the source module or submitting agent and add a stable pre-submit dedup check.",
            "actual_outcome": {
                "auto_cancelled": True,
                "decision": report.get("decision"),
                "scores": report.get("scores"),
                "rejection_reason": rejection_reason,
            },
            "summary": f"Task noise auto-cancelled: {task.title}",
        }
        result: Dict[str, Any] = {
            "status": "succeeded",
            "trace_id": trace_id,
            "memory_id": None,
            "reflection_id": None,
            "learning_trace_id": None,
            "errors": [],
        }

        if self._memory_service is not None and callable(getattr(self._memory_service, "remember", None)):
            try:
                memory = self._memory_service.remember(
                    title=f"Task noise memory: {task.title}",
                    summary=payload["summary"],
                    content=(
                        f"{root_cause}\n"
                        f"actionable_adjustment: {actionable_adjustment}\n"
                        f"rejection_reason: {rejection_reason}"
                    ),
                    layer="episodic",
                    source="task_noise_auto_cancel",
                    trace_id=trace_id,
                    target_id=task.task_id,
                    tags=["task_noise", "duplicate_task", "auto_cancelled", source_module],
                    task_id=task.task_id,
                    task_noise_report=analysis_report,
                    root_cause=root_cause,
                    actionable_adjustment=actionable_adjustment,
                )
                result["memory_id"] = str(getattr(memory, "memory_id", "") or "")
            except Exception as exc:
                result["errors"].append({"target": "memory", "error": str(exc)})

        if self._reflection_service is not None and callable(getattr(self._reflection_service, "record_nine_question_reflection", None)):
            try:
                from zentex.reflection.models import ReflectionType

                reflection = self._reflection_service.record_nine_question_reflection(
                    subject=f"Task noise reflection: {task.title}",
                    reflection_type=ReflectionType.OUTCOME_REFLECTION,
                    trace_id=trace_id,
                    context=payload,
                )
                result["reflection_id"] = str(getattr(reflection, "reflection_id", "") or "")
            except Exception as exc:
                result["errors"].append({"target": "reflection", "error": str(exc)})

        if self._learning_service is not None and callable(getattr(self._learning_service, "record_nine_question_learning", None)):
            try:
                learning = self._learning_service.record_nine_question_learning(
                    question_id=str(task.metadata.get("question_id") or "task_noise"),
                    learning_kind="task_noise_auto_cancel",
                    trace_id=trace_id,
                    detail=payload,
                )
                result["learning_trace_id"] = str(getattr(learning, "trace_id", "") or "")
            except Exception as exc:
                result["errors"].append({"target": "learning", "error": str(exc)})

        if result["errors"]:
            result["status"] = "partial" if any(result.get(key) for key in ("memory_id", "reflection_id", "learning_trace_id")) else "skipped"
        if not any((result["memory_id"], result["reflection_id"], result["learning_trace_id"])):
            result["status"] = "skipped"
            result.setdefault("reason", "memory_reflection_learning_services_not_attached_or_failed")
        self._record_audit(task.task_id, "TASK_NOISE_EXPERIENCE_WRITEBACK", result)
        return result


