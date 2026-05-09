from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType
from zentex.tasks.management.negotiation import NegotiationRequest


UTC = timezone.utc
NEGOTIATION_ENTRY_CREATED = "g5_negotiation_request_created"
NEGOTIATION_ENTRY_RESOLVED = "g5_negotiation_request_resolved"
NEGOTIATION_ENTRY_QUERIED = "g5_negotiation_requests_queried"
ACTIVE_STATUSES = {"pending", "active"}
VALID_GAP_TYPES = {"permission", "compute_resource", "human_verification", "resource_unavailable"}


async def create_resource_negotiation_request(
    kernel_service: Any,
    *,
    session_id: str,
    task_id: str,
    gap_type: str,
    required_asset: str,
    observed_error: str,
    recovery_conditions: list[str],
    task_context: dict[str, Any] | None = None,
    proposed_tradeoff: str | None = None,
    priority: int = 3,
) -> dict[str, Any]:
    """Create a G5 negotiation request and suspend the real task with recovery context."""
    state = _require_session_state(kernel_service, session_id)
    task_service = _require_task_service(kernel_service)
    normalized_gap = _validate_gap(gap_type=gap_type, required_asset=required_asset, observed_error=observed_error)
    if not recovery_conditions or not all(str(item).strip() for item in recovery_conditions):
        raise ValueError("G5 recovery_conditions must contain at least one non-empty condition")

    task = _require_task(task_service, task_id)
    existing = _find_matching_active_negotiation(task, gap_type=normalized_gap, required_asset=required_asset)
    if existing is not None:
        suspended = _require_suspended_record(task_service, task_id)
        result = _build_open_result(
            task_service=task_service,
            task_id=task_id,
            negotiation=existing,
            suspended=suspended,
            duplicate_prevented=True,
        )
        _write_transcript(
            state,
            session_id=session_id,
            event=NEGOTIATION_ENTRY_CREATED,
            payload={
                "task_id": task_id,
                "negotiation_id": existing["negotiation_id"],
                "duplicate_prevented": True,
            },
        )
        return result

    negotiation = NegotiationRequest(
        target_task_id=task_id,
        gap_type=normalized_gap,
        required_asset=str(required_asset).strip(),
        proposed_tradeoff=proposed_tradeoff,
        priority=priority,
    ).model_dump(mode="json")
    negotiation.update(
        {
            "feature_code": "G5",
            "observed_error": str(observed_error).strip(),
            "task_context": _json_safe(task_context or {}),
            "recovery_conditions": list(recovery_conditions),
            "resolution": None,
        }
    )

    if _task_status(task) != "suspended":
        await _maybe_await(
            task_service.suspend_task(
                task_id,
                reason=f"G5 {normalized_gap} gap: {required_asset}",
                recovery_conditions=recovery_conditions,
                suspension_context={
                    "feature_code": "G5",
                    "negotiation_id": negotiation["negotiation_id"],
                    "gap_type": normalized_gap,
                    "required_asset": str(required_asset).strip(),
                    "observed_error": str(observed_error).strip(),
                    "task_context": _json_safe(task_context or {}),
                },
            )
        )
    suspended = _require_suspended_record(task_service, task_id)

    task_after_suspend = _require_task(task_service, task_id)
    negotiations = _negotiations_from_task(task_after_suspend)
    negotiations.append(negotiation)
    await _persist_negotiations(
        task_service,
        task_id=task_id,
        negotiations=negotiations,
        active_negotiation_id=str(negotiation["negotiation_id"]),
        remarks="G5 negotiation request persisted",
    )
    result = _build_open_result(
        task_service=task_service,
        task_id=task_id,
        negotiation=negotiation,
        suspended=suspended,
        duplicate_prevented=False,
    )
    if result["task"]["status"] != "suspended":
        raise RuntimeError(f"G5 failed to suspend task {task_id}; queried status={result['task']['status']}")
    _write_transcript(
        state,
        session_id=session_id,
        event=NEGOTIATION_ENTRY_CREATED,
        payload={
            "task_id": task_id,
            "negotiation_id": negotiation["negotiation_id"],
            "gap_type": normalized_gap,
            "required_asset": required_asset,
            "recovery_conditions": recovery_conditions,
        },
    )
    return result


def query_resource_negotiation_requests(
    kernel_service: Any,
    *,
    session_id: str,
    task_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Query G5 negotiation requests from real task metadata and suspension state."""
    state = _require_session_state(kernel_service, session_id)
    task_service = _require_task_service(kernel_service)
    records = _collect_negotiation_records(task_service, task_id=task_id, status=status)
    payload = {
        "feature_code": "G5",
        "session_id": session_id,
        "task_id": task_id,
        "status_filter": status,
        "negotiation_count": len(records),
        "negotiations": records,
    }
    _write_transcript(
        state,
        session_id=session_id,
        event=NEGOTIATION_ENTRY_QUERIED,
        payload={"task_id": task_id, "status": status, "negotiation_count": len(records)},
    )
    return payload


async def resolve_resource_negotiation_request(
    kernel_service: Any,
    *,
    session_id: str,
    negotiation_id: str,
    approved: bool,
    resolution_note: str,
    granted_asset: str | None = None,
) -> dict[str, Any]:
    """Resolve a G5 negotiation and resume the suspended task when approved."""
    state = _require_session_state(kernel_service, session_id)
    task_service = _require_task_service(kernel_service)
    if not str(negotiation_id or "").strip():
        raise ValueError("negotiation_id is required")
    if not str(resolution_note or "").strip():
        raise ValueError("resolution_note is required")

    task, negotiations, index = _find_negotiation_owner(task_service, negotiation_id)
    negotiation = dict(negotiations[index])
    if str(negotiation.get("status")) not in ACTIVE_STATUSES:
        raise ValueError(f"G5 negotiation {negotiation_id} is not pending or active")

    negotiation["status"] = "resolved" if approved else "rejected"
    negotiation["resolution"] = {
        "approved": bool(approved),
        "resolution_note": str(resolution_note).strip(),
        "granted_asset": str(granted_asset or "").strip(),
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    negotiations[index] = negotiation
    await _persist_negotiations(
        task_service,
        task_id=task.task_id,
        negotiations=negotiations,
        active_negotiation_id="" if approved else str(negotiation_id),
        remarks="G5 negotiation request resolved",
    )

    resumed_task = None
    remaining_suspension = _get_suspended_record(task_service, task.task_id)
    if approved:
        if remaining_suspension is None:
            raise RuntimeError(f"G5 cannot resume task {task.task_id}; suspension record is missing")
        resumed_task = await _maybe_await(
            task_service.resume_task(
                task.task_id,
                remarks=f"G5 resource granted: {resolution_note}",
            )
        )
        remaining_suspension = _get_suspended_record(task_service, task.task_id)
        if remaining_suspension is not None:
            raise RuntimeError(f"G5 failed to remove suspension record for task {task.task_id}")

    queried = _collect_negotiation_records(task_service, task_id=task.task_id, status=None)
    matching = [item for item in queried if item["negotiation"]["negotiation_id"] == negotiation_id]
    if not matching:
        raise RuntimeError(f"G5 resolved negotiation {negotiation_id} is not query-visible")
    task_status = _task_status(_require_task(task_service, task.task_id))
    if approved and task_status == "suspended":
        raise RuntimeError(f"G5 approved negotiation {negotiation_id} did not resume task {task.task_id}")

    payload = {
        "feature_code": "G5",
        "session_id": session_id,
        "negotiation_id": negotiation_id,
        "approved": bool(approved),
        "task": _task_payload(_require_task(task_service, task.task_id)),
        "negotiation": matching[0]["negotiation"],
        "resumed": approved,
        "resumed_task": _task_payload(resumed_task) if resumed_task is not None else None,
        "remaining_suspension": _model_dump(remaining_suspension),
    }
    _write_transcript(
        state,
        session_id=session_id,
        event=NEGOTIATION_ENTRY_RESOLVED,
        payload={
            "task_id": task.task_id,
            "negotiation_id": negotiation_id,
            "approved": approved,
            "task_status": payload["task"]["status"],
        },
    )
    return payload


def _require_session_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for G5 resource negotiation: {session_id}")
    return state


def _require_task_service(kernel_service: Any) -> Any:
    task_service = getattr(kernel_service, "_task_service", None)
    if task_service is None:
        raise RuntimeError("G5 resource negotiation requires an attached task service")
    for method_name in ("get_task", "suspend_task", "resume_task", "update_task_metadata", "list_tasks"):
        if not callable(getattr(task_service, method_name, None)):
            raise RuntimeError(f"G5 task service missing required method: {method_name}")
    return task_service


def _validate_gap(*, gap_type: str, required_asset: str, observed_error: str) -> str:
    normalized = str(gap_type or "").strip().lower()
    if normalized not in VALID_GAP_TYPES:
        raise ValueError(f"Unsupported G5 gap_type: {gap_type}")
    if not str(required_asset or "").strip():
        raise ValueError("required_asset is required")
    error_text = str(observed_error or "").strip()
    if not error_text:
        raise ValueError("observed_error is required")
    if normalized == "permission":
        lowered = error_text.lower()
        if not any(token in lowered for token in ("permission", "denied", "access", "unauthorized", "forbidden")):
            raise ValueError("permission gap requires observed_error evidence of denied access")
    return normalized


def _require_task(task_service: Any, task_id: str) -> Any:
    task = task_service.get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found for G5 negotiation: {task_id}")
    return task


def _get_suspended_record(task_service: Any, task_id: str) -> Any:
    return task_service.get_suspended_task(task_id)


def _require_suspended_record(task_service: Any, task_id: str) -> Any:
    suspended = _get_suspended_record(task_service, task_id)
    if suspended is None:
        raise RuntimeError(f"G5 expected suspended task record for {task_id}, but none was query-visible")
    return suspended


def _find_matching_active_negotiation(task: Any, *, gap_type: str, required_asset: str) -> dict[str, Any] | None:
    for item in _negotiations_from_task(task):
        if (
            str(item.get("gap_type")) == gap_type
            and str(item.get("required_asset")) == str(required_asset)
            and str(item.get("status")) in ACTIVE_STATUSES
        ):
            return dict(item)
    return None


def _negotiations_from_task(task: Any) -> list[dict[str, Any]]:
    metadata = getattr(task, "metadata", {}) or {}
    rows = metadata.get("g5_resource_negotiations") or []
    if not isinstance(rows, list):
        raise RuntimeError(f"Task {getattr(task, 'task_id', '')} has invalid G5 negotiation metadata")
    return [dict(item) for item in rows if isinstance(item, dict)]


async def _persist_negotiations(
    task_service: Any,
    *,
    task_id: str,
    negotiations: list[dict[str, Any]],
    active_negotiation_id: str,
    remarks: str,
) -> None:
    await _maybe_await(
        task_service.update_task_metadata(
            task_id,
            {
                "g5_resource_negotiations": _json_safe(negotiations),
                "g5_active_negotiation_id": active_negotiation_id,
                "g5_updated_at": datetime.now(UTC).isoformat(),
            },
            remarks=remarks,
        )
    )


def _collect_negotiation_records(
    task_service: Any,
    *,
    task_id: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    if task_id:
        tasks = [_require_task(task_service, task_id)]
    else:
        tasks = list(task_service.list_tasks())
    records: list[dict[str, Any]] = []
    for task in tasks:
        suspended = _get_suspended_record(task_service, task.task_id)
        for negotiation in _negotiations_from_task(task):
            if status and str(negotiation.get("status")) != status:
                continue
            records.append(
                {
                    "task": _task_payload(task),
                    "negotiation": dict(negotiation),
                    "suspended_task": _model_dump(suspended),
                    "recovery_ready": suspended is None and str(negotiation.get("status")) == "resolved",
                }
            )
    records.sort(key=lambda item: str(item["negotiation"].get("created_at", "")), reverse=True)
    return records


def _find_negotiation_owner(task_service: Any, negotiation_id: str) -> tuple[Any, list[dict[str, Any]], int]:
    for task in task_service.list_tasks():
        negotiations = _negotiations_from_task(task)
        for index, item in enumerate(negotiations):
            if str(item.get("negotiation_id")) == str(negotiation_id):
                return task, negotiations, index
    raise ValueError(f"G5 negotiation not found: {negotiation_id}")


def _build_open_result(
    *,
    task_service: Any,
    task_id: str,
    negotiation: dict[str, Any],
    suspended: Any,
    duplicate_prevented: bool,
) -> dict[str, Any]:
    return {
        "feature_code": "G5",
        "task": _task_payload(_require_task(task_service, task_id)),
        "negotiation": dict(negotiation),
        "suspended_task": _model_dump(suspended),
        "duplicate_prevented": duplicate_prevented,
    }


def _task_payload(task: Any) -> dict[str, Any]:
    if task is None:
        return {}
    return {
        "task_id": str(task.task_id),
        "title": str(task.title),
        "status": _task_status(task),
        "priority": str(getattr(getattr(task, "priority", ""), "value", getattr(task, "priority", ""))),
        "metadata": _json_safe(getattr(task, "metadata", {}) or {}),
    }


def _task_status(task: Any) -> str:
    status = getattr(task, "status", "")
    return str(getattr(status, "value", status))


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return _json_safe(value)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _write_transcript(
    state: Any,
    *,
    session_id: str,
    event: str,
    payload: dict[str, Any],
) -> None:
    transcript = getattr(state, "transcript", None)
    if transcript is None:
        raise RuntimeError("G5 resource negotiation requires a session transcript store")
    trace_id = f"g5-resource-negotiation:{payload.get('negotiation_id') or uuid4().hex}"
    transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=session_id,
            turn_id=f"g5-{uuid4().hex}",
            trace_id=trace_id,
            source="kernel.resource_negotiation",
            payload={
                "feature_code": "G5",
                "entry_type": event,
                "trace_id": trace_id,
                **_json_safe(payload),
            },
        )
    )


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
