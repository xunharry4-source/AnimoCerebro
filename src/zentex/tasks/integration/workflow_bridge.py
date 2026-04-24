from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional, Union

from zentex.supervision.integration import (
    SupervisedTaskManager,
    create_supervised_task_manager,
)
from zentex.tasks.models import TaskPriority, TaskStatus, TaskType
from zentex.tasks.service import TaskManagementService, get_service as get_task_service


logger = logging.getLogger(__name__)


class WorkflowTaskBridge:
    """Sync reflection and upgrade workflows into unified task management."""

    def __init__(
        self,
        *,
        task_service: Optional[TaskManagementService] = None,
        supervised_manager: Optional[SupervisedTaskManager] = None,
    ) -> None:
        self._task_service = task_service or get_task_service()
        self._supervised_manager = supervised_manager or create_supervised_task_manager(
            self._task_service
        )

    def sync_reflection_submission(
        self,
        *,
        task_id: str,
        subject: str,
        reflection_type: str,
        priority: Any,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> str:
        task = self._ensure_task(
            idempotency_key=f"reflection:{task_id}",
            title=f"Reflection: {subject}",
            task_type=TaskType.COGNITIVE_STEP,
            originator_id="reflection.async_service",
            priority=self._map_priority(priority),
            remarks=f"Reflection task {task_id} ({reflection_type})",
            tags=["reflection", reflection_type],
            metadata={
                "source_module": "reflection",
                "source_task_id": task_id,
                "reflection_type": reflection_type,
                "trace_id": trace_id,
                "session_id": session_id,
                "template_id": template_id,
            },
        )
        return task.task_id

    def sync_reflection_status(
        self,
        task_id: str,
        status: str,
        *,
        subject: Optional[str] = None,
        reflection_type: Optional[str] = None,
        remarks: Optional[str] = None,
    ) -> str:
        task = self._ensure_task(
            idempotency_key=f"reflection:{task_id}",
            title=f"Reflection: {subject or task_id}",
            task_type=TaskType.COGNITIVE_STEP,
            originator_id="reflection.async_service",
            priority=TaskPriority.MEDIUM,
            remarks=remarks or f"Reflection task {task_id}",
            tags=["reflection", str(reflection_type or "unknown")],
            metadata={
                "source_module": "reflection",
                "source_task_id": task_id,
                "reflection_type": reflection_type,
            },
        )
        self._transition_task(
            task.task_id,
            self._map_reflection_status(status),
            remarks or f"Reflection status -> {status}",
        )
        self._update_task_tracking(
            task.task_id,
            {
                "workflow_status": str(status),
                "workflow_kind": "reflection",
            },
            remarks=remarks or f"Reflection status -> {status}",
        )
        return task.task_id

    def sync_upgrade_record(self, record: Any) -> str:
        record_id = str(getattr(record, "record_id"))
        status = str(
            getattr(getattr(record, "current_status", None), "value", getattr(record, "current_status", ""))
        )
        progress = int(getattr(record, "current_progress", 0) or 0)
        task = self._ensure_task(
            idempotency_key=f"upgrade:{record_id}",
            title=str(getattr(record, "title", f"Upgrade {record_id}")),
            task_type=TaskType.SYSTEM_ACTION,
            originator_id="upgrade.execution_service",
            priority=TaskPriority.HIGH,
            target_id=str(getattr(record, "target_id", "") or ""),
            remarks=str(getattr(record, "reason", "") or f"Upgrade record {record_id}"),
            tags=["upgrade", str(getattr(record, "action", "upgrade"))],
            metadata={
                "source_module": "upgrade",
                "record_id": record_id,
                "trace_id": str(getattr(record, "trace_id", "") or ""),
                "request_id": str(getattr(record, "request_id", "") or ""),
            },
        )
        self._transition_task(
            task.task_id,
            self._map_upgrade_status(status),
            f"Upgrade status -> {status}",
        )
        self._update_task_tracking(
            task.task_id,
            {
                "workflow_kind": "upgrade",
                "workflow_status": status,
                "workflow_progress": progress,
                "upgrade_action": str(getattr(record, "action", "upgrade")),
                "upgrade_target_kind": str(
                    getattr(getattr(record, "target_kind", None), "value", getattr(record, "target_kind", ""))
                ),
                "candidate_version": str(getattr(record, "candidate_version", "") or ""),
            },
            remarks=f"Upgrade status -> {status}",
        )
        self._update_supervision_record(
            task.task_id,
            parameters={
                "workflow_status": status,
                "workflow_progress": progress,
                "upgrade_action": str(getattr(record, "action", "upgrade")),
                "record_id": record_id,
            },
            note=f"Upgrade stage {status} ({progress}%)",
            completed=status == "completed",
            failed=status == "failed",
        )
        return task.task_id

    def list_reflection_tasks(self) -> list[Any]:
        return self._task_service.list_tasks(source_module="reflection")

    def list_upgrade_tasks(self) -> list[Any]:
        return self._task_service.list_tasks(source_module="upgrade")

    def _ensure_task(self, **payload: Any):
        return self._run_coroutine(self._supervised_manager.create_and_supervise_task(payload))

    def _transition_task(self, task_id: str, target_status: TaskStatus, remarks: str) -> None:
        task = self._task_service.get_task(task_id)
        if task is None or task.status == target_status:
            return
        try:
            if task.status == TaskStatus.TODO and target_status == TaskStatus.DONE:
                self._task_service.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks="Auto-start for workflow bridge")
            self._task_service.update_task_status(task_id, target_status, remarks=remarks)
        except Exception as exc:
            logger.warning("workflow bridge failed to update task %s: %s", task_id, exc)

    def _update_task_tracking(
        self, task_id: str, metadata_updates: dict[str, Any], *, remarks: Optional[str] = None
    ) -> None:
        try:
            self._task_service.update_task_metadata(
                task_id,
                metadata_updates,
                remarks=remarks,
            )
        except Exception as exc:
            logger.warning("workflow bridge failed to update task metadata %s: %s", task_id, exc)

    def _update_supervision_record(
        self,
        task_id: str,
        *,
        parameters: dict[str, Any],
        note: str,
        completed: bool = False,
        failed: bool = False,
    ) -> None:
        record = self._supervised_manager.task_supervisor.get_task_supervision_status(task_id)
        if record is None:
            return
        record.parameters.update(parameters)
        record.supervisor_notes.append(note)
        if completed:
            self._supervised_manager.task_supervisor.complete_task_supervision(task_id, True, parameters)
        elif failed:
            self._supervised_manager.task_supervisor.complete_task_supervision(task_id, False, note)

    def _run_coroutine(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:  # pragma: no cover
                error["value"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if "value" in error:
            raise error["value"]
        return result["value"]

    def _map_priority(self, priority: Any) -> TaskPriority:
        raw = str(getattr(priority, "value", priority)).lower()
        if raw in {"0", "critical"}:
            return TaskPriority.CRITICAL
        if raw in {"1", "high"}:
            return TaskPriority.HIGH
        if raw in {"3", "low"}:
            return TaskPriority.LOW
        return TaskPriority.MEDIUM

    def _map_reflection_status(self, status: str) -> TaskStatus:
        normalized = str(status).strip().lower()
        if normalized in {"running", "in_progress"}:
            return TaskStatus.IN_PROGRESS
        if normalized in {"completed", "done"}:
            return TaskStatus.DONE
        if normalized in {"failed", "error"}:
            return TaskStatus.FAILED
        if normalized in {"cancelled", "canceled"}:
            return TaskStatus.ARCHIVED
        return TaskStatus.TODO

    def _map_upgrade_status(self, status: str) -> TaskStatus:
        normalized = str(status).strip().lower()
        if normalized == "queued":
            return TaskStatus.TODO
        if normalized in {
            "planning",
            "copying_source",
            "scaffolding_candidate",
            "running",
            "validating",
            "registered",
            "active",
        }:
            return TaskStatus.IN_PROGRESS
        if normalized == "completed":
            return TaskStatus.DONE
        if normalized == "failed":
            return TaskStatus.FAILED
        if normalized in {"cancelled", "cleaned_up"}:
            return TaskStatus.ARCHIVED
        return TaskStatus.TODO
