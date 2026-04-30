from __future__ import annotations

"""Task-center writeback helpers for internally dispatched external executors.

The bridge is intentionally host-side only.  It records Zentex task lifecycle
state around CLI/MCP calls without requiring external CLI binaries or MCP
servers to understand task IDs, traces, or task-center contracts.
"""

import inspect
from typing import Any, Dict, Optional

from zentex.tasks.models import TaskStatus


class ExternalExecutionWritebackError(RuntimeError):
    """Raised when an external execution result cannot be written to tasks."""


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _status_value(task: Any) -> str:
    status = getattr(task, "status", None)
    return getattr(status, "value", status) or ""


def _task_payload(task: Any) -> Dict[str, Any]:
    if hasattr(task, "model_dump"):
        return task.model_dump(mode="json")
    return dict(task or {})


async def mark_external_execution_started(
    *,
    task_service: Any,
    task_id: str,
    trace_id: str,
    executor_type: str,
    executor_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Ensure a task is in-progress before an external executor is invoked."""
    if task_service is None:
        raise ExternalExecutionWritebackError("TaskManagementService is required for external execution writeback")
    if not task_id:
        raise ExternalExecutionWritebackError("task_id is required for task-center dispatched external execution")

    task = task_service.get_task(task_id)
    if task is None:
        raise ExternalExecutionWritebackError(f"Task {task_id} not found")

    status = _status_value(task)
    if status == TaskStatus.TODO.value:
        task = await _await_if_needed(
            task_service.update_task_status(
                task_id,
                TaskStatus.IN_PROGRESS,
                remarks=f"{executor_type} execution started",
            )
        )
    elif status != TaskStatus.IN_PROGRESS.value:
        raise ExternalExecutionWritebackError(
            f"Task {task_id} cannot be dispatched to {executor_type} from status {status}"
        )

    metadata = {
        "external_execution": {
            "executor_type": executor_type,
            "trace_id": trace_id,
            "phase": "started",
            **executor_metadata,
        },
        "trace_id": trace_id,
        **executor_metadata,
    }
    updated_task = await _await_if_needed(
        task_service.update_task_metadata(
            task_id,
            metadata,
            remarks=f"{executor_type} execution started",
        )
    )
    return _task_payload(updated_task)


async def write_external_execution_result(
    *,
    task_service: Any,
    task_id: str,
    trace_id: str,
    executor_type: str,
    executor_metadata: Dict[str, Any],
    result_payload: Dict[str, Any],
    succeeded: bool,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist final CLI/MCP execution result through TaskManagementService."""
    if task_service is None:
        raise ExternalExecutionWritebackError("TaskManagementService is required for external execution writeback")
    if not task_id:
        raise ExternalExecutionWritebackError("task_id is required for task-center dispatched external execution")

    status = "completed" if succeeded else "failed"
    metadata = {
        "external_execution": {
            "executor_type": executor_type,
            "trace_id": trace_id,
            "phase": status,
            "result": result_payload,
            "error": error_message,
            **executor_metadata,
        },
        "trace_id": trace_id,
        "execution_status": status,
        "execution_result_summary": _summarize_result(result_payload),
        **executor_metadata,
    }
    if error_message:
        metadata["external_execution_error"] = error_message

    await _await_if_needed(
        task_service.update_task_metadata(
            task_id,
            metadata,
            remarks=f"{executor_type} execution {status}",
        )
    )

    if succeeded:
        completion = await _await_if_needed(
            task_service.complete_task_with_verification(
                task_id,
                result={
                    "actual_outcome": result_payload,
                    "external_execution": {
                        "executor_type": executor_type,
                        "trace_id": trace_id,
                        **executor_metadata,
                    },
                },
                remarks=f"{executor_type} execution completed",
            )
        )
        if not isinstance(completion, dict) or completion.get("success") is not True:
            raise ExternalExecutionWritebackError(
                f"Task {task_id} completion writeback failed: {completion}"
            )
        return completion

    failed_task = await _await_if_needed(
        task_service.update_task_status(
            task_id,
            TaskStatus.FAILED,
            remarks=error_message or f"{executor_type} execution failed",
        )
    )
    return {
        "success": False,
        "task": _task_payload(failed_task),
        "error": error_message,
        "error_code": "EXTERNAL_EXECUTION_FAILED",
    }


def _summarize_result(result_payload: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for key in (
        "status",
        "exit_code",
        "failure_category",
        "error_code",
        "error_message",
        "duration_ms",
        "duration_seconds",
        "stdout",
        "stderr",
        "payload",
    ):
        if key not in result_payload:
            continue
        value = result_payload.get(key)
        if isinstance(value, str) and len(value) > 500:
            value = value[:500]
        summary[key] = value
    return summary
