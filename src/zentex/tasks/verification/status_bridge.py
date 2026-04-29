from __future__ import annotations

from typing import Any

from zentex.tasks.models.errors import TaskStateError
from zentex.tasks.models import TaskStatus


def _verification_enabled(task: Any) -> bool:
    contract = getattr(task, "contract", None)
    verification = getattr(contract, "verification", None)
    return bool(getattr(verification, "enabled", False))


def _should_route_done_update(task: Any, new_status: TaskStatus) -> bool:
    if new_status != TaskStatus.DONE:
        return False
    if getattr(task, "status", None) == TaskStatus.WAITING_CONFIRMATION:
        return False
    return _verification_enabled(task)


def _build_direct_done_receipt(task_id: str, remarks: Any) -> dict[str, Any]:
    return {
        "actual_outcome": {
            "task_id": task_id,
            "status_update_request": True,
            "requested_status": TaskStatus.DONE.value,
            "remarks": remarks,
        },
        "status_update_bridge": {
            "source": "update_task_status",
            "requires_external_evidence": True,
            "reason": "direct_done_status_update_must_pass_verification",
        },
    }


def _bridge_error_message(task_id: str, completion: dict[str, Any]) -> str:
    verification_result = completion.get("verification_result")
    verification_result = verification_result if isinstance(verification_result, dict) else {}
    return (
        "Direct DONE status update for task "
        f"{task_id} was routed through verification and rejected: "
        f"{verification_result.get('summary') or completion.get('message') or completion.get('error')}"
    )


async def maybe_route_done_status_update_through_verification(
    task_service: Any,
    *,
    task: Any,
    task_id: str,
    new_status: TaskStatus,
    remarks: Any,
) -> Any | None:
    if not _should_route_done_update(task, new_status):
        return None

    completion = await task_service.complete_task_with_verification(
        task_id,
        result=_build_direct_done_receipt(task_id, remarks),
        remarks=(
            "Direct DONE status update routed through verification bridge. "
            "External evidence is required for acceptance."
        ),
    )
    completion = completion if isinstance(completion, dict) else {}
    if completion.get("success") is True:
        return task_service.get_task(task_id)
    raise TaskStateError(_bridge_error_message(task_id, completion))
