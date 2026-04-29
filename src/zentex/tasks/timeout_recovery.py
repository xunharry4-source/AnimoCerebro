from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from zentex.tasks.models import TaskStatus, ZentexTask


RECOVERY_SOURCE = "check_timeout_and_republish_tasks"


@dataclass(frozen=True)
class TimeoutRecoveryAction:
    task_id: str
    new_status: TaskStatus
    metadata: Dict[str, Any]
    remarks: str
    result: Dict[str, Any]
    last_error: Optional[str] = None
    execution_finished_at: Optional[str] = None


def build_timeout_recovery_action(
    task: ZentexTask,
    *,
    now: datetime,
) -> Optional[TimeoutRecoveryAction]:
    lease = task.metadata.get("lease")
    if not isinstance(lease, dict):
        return _blocked_runtime_state_action(
            task,
            now=now,
            recovery_error="missing_lease",
            required_action="operator_review_missing_lease",
            message=f"Task {task.task_id} is in_progress without lease metadata.",
        )

    try:
        heartbeat_at = _parse_lease_timestamp(
            lease.get("heartbeat_at") or lease.get("acquired_at"),
            task_id=task.task_id,
            field_name="heartbeat_at",
        )
    except ValueError as exc:
        return _blocked_runtime_state_action(
            task,
            now=now,
            recovery_error="malformed_lease_timestamp",
            required_action="operator_review_malformed_lease",
            message=str(exc),
        )

    timeout_seconds_raw = lease.get("timeout_seconds", 300)
    try:
        timeout_seconds = int(timeout_seconds_raw)
    except (TypeError, ValueError):
        return _blocked_runtime_state_action(
            task,
            now=now,
            recovery_error="invalid_lease_timeout",
            required_action="operator_review_malformed_lease",
            message=f"Task {task.task_id} has invalid lease timeout_seconds={timeout_seconds_raw!r}.",
        )
    if timeout_seconds <= 0:
        return _blocked_runtime_state_action(
            task,
            now=now,
            recovery_error="invalid_lease_timeout",
            required_action="operator_review_malformed_lease",
            message=f"Task {task.task_id} has invalid lease timeout_seconds={timeout_seconds_raw!r}.",
        )

    elapsed_seconds = (now - heartbeat_at).total_seconds()
    if elapsed_seconds <= timeout_seconds:
        return None

    next_status = TaskStatus.TODO if task.contract.retriable else TaskStatus.FAILED
    metadata = copy.deepcopy(task.metadata)
    metadata["lease"] = {
        **lease,
        "status": "expired",
        "expired_at": now.isoformat(),
        "heartbeat_at": heartbeat_at.isoformat(),
        "timeout_seconds": timeout_seconds,
    }
    metadata["timeout_recovery"] = {
        "timed_out": True,
        "detected_at": now.isoformat(),
        "heartbeat_at": heartbeat_at.isoformat(),
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": elapsed_seconds,
        "recovery_source": RECOVERY_SOURCE,
        "previous_status": task.status.value,
    }
    remarks = (
        f"Timeout recovery after {elapsed_seconds:.0f}s without heartbeat; "
        f"lease expired at {now.isoformat()}."
    )
    return TimeoutRecoveryAction(
        task_id=task.task_id,
        new_status=next_status,
        metadata=metadata,
        remarks=remarks,
        result={
            "task_id": task.task_id,
            "republished": next_status == TaskStatus.TODO,
            "new_status": next_status.value,
            "timeout_seconds": timeout_seconds,
            "elapsed_seconds": elapsed_seconds,
            "recovery_error": None,
        },
    )


def _blocked_runtime_state_action(
    task: ZentexTask,
    *,
    now: datetime,
    recovery_error: str,
    required_action: str,
    message: str,
) -> TimeoutRecoveryAction:
    metadata = copy.deepcopy(task.metadata)
    metadata["timeout_recovery"] = {
        "timed_out": False,
        "detected_at": now.isoformat(),
        "recovery_source": RECOVERY_SOURCE,
        "previous_status": task.status.value,
        "recovery_error": recovery_error,
        "required_action": required_action,
        "message": message,
    }
    return TimeoutRecoveryAction(
        task_id=task.task_id,
        new_status=TaskStatus.BLOCKED,
        metadata=metadata,
        remarks=message,
        last_error=message,
        execution_finished_at=now.isoformat(),
        result={
            "task_id": task.task_id,
            "republished": False,
            "new_status": TaskStatus.BLOCKED.value,
            "timeout_seconds": None,
            "elapsed_seconds": None,
            "recovery_error": recovery_error,
            "required_action": required_action,
            "message": message,
        },
    )


def _parse_lease_timestamp(
    raw_value: Any,
    *,
    task_id: str,
    field_name: str,
) -> datetime:
    if not raw_value or not isinstance(raw_value, str):
        raise ValueError(
            f"Task {task_id} lease field '{field_name}' is missing or not an ISO timestamp."
        )

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Task {task_id} lease field '{field_name}' is not an ISO timestamp: {raw_value!r}."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
