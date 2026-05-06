from __future__ import annotations

"""Task-center writeback helpers for internally dispatched external executors.

The bridge is intentionally host-side only.  It records Zentex task lifecycle
state around CLI/MCP calls without requiring external CLI binaries or MCP
servers to understand task IDs, traces, or task-center contracts.
"""

import inspect
import json
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


def _persist_execution_output(task_service: Any, task_id: str, payload: Dict[str, Any]) -> None:
    dao = getattr(task_service, "_task_dao", None)
    if dao is not None:
        dao.update_task(task_id, {"execution_output": json.dumps(payload, ensure_ascii=False, default=str)})


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
    if status in {TaskStatus.TODO.value, TaskStatus.QUEUED.value}:
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

    execution_evidence = {
        "executor_type": executor_type,
        "trace_id": trace_id,
        "executor_metadata": dict(executor_metadata or {}),
        "result_status": result_payload.get("status"),
        "exit_code": result_payload.get("exit_code"),
        "duration_ms": result_payload.get("duration_ms"),
        "payload_present": bool(result_payload),
        "evidence_ref": f"external_execution:{executor_type}:{task_id}:{trace_id}",
    }

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
                    "evidence": execution_evidence,
                },
                remarks=f"{executor_type} execution completed",
            )
        )
        if not isinstance(completion, dict) or completion.get("success") is not True:
            raise ExternalExecutionWritebackError(
                f"Task {task_id} completion writeback failed: {completion}"
            )
        _persist_execution_output(
            task_service,
            task_id,
            {
                "succeeded": True,
                "task_center_synchronized": True,
                "executor_type": executor_type,
                "trace_id": trace_id,
                "result": result_payload,
                "action_execution_receipt": execution_evidence,
                "completion": completion,
            },
        )
        return completion

    failed_task = await _await_if_needed(
        task_service.update_task_status(
            task_id,
            TaskStatus.FAILED,
            remarks=error_message or f"{executor_type} execution failed",
        )
    )
    _persist_execution_output(
        task_service,
        task_id,
        {
            "succeeded": False,
            "task_center_synchronized": True,
            "executor_type": executor_type,
            "trace_id": trace_id,
            "result": result_payload,
            "error": error_message,
            "action_execution_receipt": execution_evidence,
        },
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
