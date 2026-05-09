from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Iterable

from zentex.common.workflow_errors import WorkflowExecutionError


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _status_value(task: Any) -> str:
    if task is None:
        return ""
    status = task.get("status") if isinstance(task, dict) else getattr(task, "status", None)
    return str(getattr(status, "value", status) or "")


def _task_payload(task: Any) -> dict[str, Any]:
    if task is None:
        return {}
    if hasattr(task, "model_dump"):
        return task.model_dump(mode="json")
    if isinstance(task, dict):
        return dict(task)
    return {
        "task_id": getattr(task, "task_id", ""),
        "status": _status_value(task),
        "metadata": getattr(task, "metadata", {}),
    }


async def wait_for_task_status(
    task_service: Any,
    task_id: str,
    target_statuses: Iterable[str],
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.25,
) -> dict[str, Any]:
    """Poll the real task service until a task reaches one of the target statuses."""
    if task_service is None or not callable(getattr(task_service, "get_task", None)):
        raise WorkflowExecutionError(
            "task_service.get_task is required",
            error_code="TASK_SERVICE_QUERY_METHOD_MISSING",
        )
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        raise WorkflowExecutionError("task_id is required", error_code="TASK_ID_MISSING")
    targets = {str(item).strip() for item in target_statuses if str(item).strip()}
    if not targets:
        raise WorkflowExecutionError("target_statuses cannot be empty", error_code="TASK_TARGET_STATUS_MISSING")

    started = time.monotonic()
    last_task: Any = None
    last_status = ""
    while True:
        try:
            last_task = await _await_if_needed(task_service.get_task(normalized_task_id))
        except Exception as exc:
            raise WorkflowExecutionError(
                f"Failed to read task {normalized_task_id}: {exc}",
                error_code="TASK_READ_FAILED",
                context={"task_id": normalized_task_id},
            ) from exc
        last_status = _status_value(last_task)
        if last_status in targets:
            return {
                "status": "succeeded",
                "error_code": "",
                "trace_id": str((_task_payload(last_task).get("metadata") or {}).get("trace_id") or ""),
                "session_id": str((_task_payload(last_task).get("metadata") or {}).get("session_id") or ""),
                "task_id": normalized_task_id,
                "node_id": "task-sync",
                "node_name": "Task Status Wait",
                "evidence_ref": f"task:{normalized_task_id}",
                "evidence": {
                    "target_statuses": sorted(targets),
                    "actual_status": last_status,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "task": _task_payload(last_task),
                },
                "failures": [],
            }
        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            return {
                "status": "failed",
                "error_code": "TASK_WAIT_TIMEOUT",
                "trace_id": str((_task_payload(last_task).get("metadata") or {}).get("trace_id") or ""),
                "session_id": str((_task_payload(last_task).get("metadata") or {}).get("session_id") or ""),
                "task_id": normalized_task_id,
                "node_id": "task-sync",
                "node_name": "Task Status Wait",
                "evidence_ref": f"task:{normalized_task_id}",
                "evidence": {
                    "target_statuses": sorted(targets),
                    "actual_status": last_status,
                    "elapsed_seconds": round(elapsed, 3),
                    "timeout_seconds": timeout_seconds,
                    "task": _task_payload(last_task),
                },
                "failures": [
                    {
                        "reason": "task_wait_timeout",
                        "error_code": "TASK_WAIT_TIMEOUT",
                        "task_id": normalized_task_id,
                        "target_statuses": sorted(targets),
                        "actual_status": last_status,
                    }
                ],
            }
        await asyncio.sleep(max(0.05, poll_interval_seconds))


async def recover_waiting_confirmation_task(
    *,
    task_service: Any,
    task_id: str,
    trace_id: str,
    session_id: str,
    audit_service: Any = None,
    remarks: str = "Operator confirmed; task returned to todo for worker pickup.",
) -> dict[str, Any]:
    if task_service is None or not callable(getattr(task_service, "get_task", None)):
        raise WorkflowExecutionError(
            "task_service.get_task is required",
            error_code="TASK_SERVICE_QUERY_METHOD_MISSING",
        )
    task = await _await_if_needed(task_service.get_task(task_id))
    if _status_value(task) != "waiting_confirmation":
        raise WorkflowExecutionError(
            f"Task {task_id} is not waiting for confirmation",
            error_code="TASK_NOT_WAITING_CONFIRMATION",
            context={"task_id": task_id, "actual_status": _status_value(task)},
        )
    if not callable(getattr(task_service, "update_task_status", None)):
        raise WorkflowExecutionError(
            "task_service.update_task_status is required",
            error_code="TASK_SERVICE_UPDATE_METHOD_MISSING",
        )
    from zentex.tasks.models import TaskStatus

    resumed = await _await_if_needed(
        task_service.update_task_status(
            task_id,
            TaskStatus.IN_PROGRESS,
            remarks="Operator confirmed; task is resuming before worker requeue.",
        )
    )
    updated = await _await_if_needed(task_service.update_task_status(task_id, TaskStatus.TODO, remarks=remarks))
    from zentex.audit.workflow_events import record_workflow_node_event

    audit = record_workflow_node_event(
        audit_service=audit_service,
        event_type="posture_recovered",
        node_id="hitl-recovery",
        node_name="Human Confirmation Recovery",
        status="succeeded",
        trace_id=trace_id,
        session_id=session_id,
        task_id=task_id,
        input_summary={"previous_status": "waiting_confirmation"},
        output_summary={"intermediate_status": "in_progress", "new_status": "todo", "remarks": remarks},
        evidence_ref=f"task:{task_id}:posture_recovered",
        source="zentex.tasks.execution.workflow_sync",
    )
    return {
        "status": "succeeded",
        "error_code": "",
        "trace_id": trace_id,
        "session_id": session_id,
        "task_id": task_id,
        "node_id": "hitl-recovery",
        "node_name": "Human Confirmation Recovery",
        "evidence_ref": audit["evidence_ref"],
        "evidence": {"resumed_task": _task_payload(resumed), "task": _task_payload(updated), "audit": audit},
        "failures": [],
    }
