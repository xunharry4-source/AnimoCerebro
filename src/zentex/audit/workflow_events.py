from __future__ import annotations

import json
from typing import Any

from zentex.common.workflow_errors import WorkflowAuditChainError
from zentex.common.workflow_models import WorkflowNodeStatus, WorkflowRunContext, normalize_status


STANDARD_WORKFLOW_EVENTS = {
    "workflow_started",
    "question_output_checked",
    "node_started",
    "node_succeeded",
    "node_failed",
    "node_blocked",
    "node_degraded",
    "task_generated",
    "task_persisted",
    "task_created",
    "dispatch_started",
    "dispatch_reassigned",
    "external_invoked",
    "executor_invocation_finished",
    "dependency_failed",
    "side_effect_verified",
    "task_outcome_recorded",
    "verification_finished",
    "human_confirmation_requested",
    "human_confirmation_recorded",
    "memory_writeback_finished",
    "learning_writeback_finished",
    "reflection_writeback_finished",
    "writeback_verified",
    "maintenance_started",
    "maintenance_finished",
    "posture_recovered",
    "workflow_finished",
    "workflow_failed",
}


def _require_text(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise WorkflowAuditChainError(
            f"{field_name} is required for workflow audit events",
            error_code="WORKFLOW_AUDIT_FIELD_MISSING",
            context={"field": field_name},
        )
    return normalized


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _context_value(context: WorkflowRunContext | dict[str, Any] | None, key: str, default: str = "") -> str:
    if context is None:
        return default
    if isinstance(context, WorkflowRunContext):
        return str(getattr(context, key, default) or default)
    if isinstance(context, dict):
        return str(context.get(key) or default)
    return default


def record_workflow_node_event(
    *,
    audit_service: Any = None,
    context: WorkflowRunContext | dict[str, Any] | None = None,
    event_type: str,
    node_id: str,
    node_name: str,
    status: WorkflowNodeStatus | str,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    evidence_ref: str = "",
    error_code: str = "",
    task_id: str = "",
    trace_id: str = "",
    session_id: str = "",
    turn_id: str = "",
    source: str = "zentex.audit.workflow_events",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one standard full-workflow node event to the unified audit chain.

    This helper is intentionally fail-closed. A missing audit service method or
    failed write raises WorkflowAuditChainError instead of returning a synthetic
    success.
    """
    if event_type not in STANDARD_WORKFLOW_EVENTS:
        raise WorkflowAuditChainError(
            f"Unsupported workflow audit event type: {event_type}",
            error_code="WORKFLOW_AUDIT_EVENT_UNSUPPORTED",
            context={"event_type": event_type},
        )

    normalized_node_id = _require_text(node_id, "node_id")
    normalized_node_name = _require_text(node_name, "node_name")
    normalized_trace_id = _require_text(trace_id or _context_value(context, "trace_id"), "trace_id")
    normalized_session_id = _require_text(session_id or _context_value(context, "session_id"), "session_id")
    normalized_task_id = str(task_id or _context_value(context, "task_id") or "").strip()
    normalized_turn_id = str(turn_id or _context_value(context, "turn_id") or normalized_session_id).strip()
    normalized_status = _require_text(normalize_status(status), "status")

    if audit_service is None:
        from zentex.audit.service import get_service

        audit_service = get_service()
    record = getattr(audit_service, "record_audit_entry", None)
    if not callable(record):
        raise WorkflowAuditChainError(
            "audit_service.record_audit_entry is required",
            error_code="WORKFLOW_AUDIT_SERVICE_INVALID",
        )

    payload = {
        "workflow_event_type": event_type,
        "node_id": normalized_node_id,
        "node_name": normalized_node_name,
        "node_ref": f"{normalized_node_id}-{normalized_node_name}",
        "status": normalized_status,
        "trace_id": normalized_trace_id,
        "session_id": normalized_session_id,
        "turn_id": normalized_turn_id,
        "task_id": normalized_task_id,
        "input_summary": _json_safe(input_summary or {}),
        "output_summary": _json_safe(output_summary or {}),
        "evidence_ref": str(evidence_ref or ""),
        "error_code": str(error_code or ""),
        "details": _json_safe(details or {}),
    }
    try:
        entry_id = record(
            trace_id=normalized_trace_id,
            session_id=normalized_session_id,
            turn_id=normalized_turn_id,
            entry_type="workflow",
            source=source,
            summary=f"{event_type}: {normalized_node_id}-{normalized_node_name} [{normalized_status}]",
            question_driver_refs=[normalized_node_id],
            context_info={
                "status": normalized_status,
                "node_id": normalized_node_id,
                "node_name": normalized_node_name,
                "task_id": normalized_task_id,
                "workflow_event_type": event_type,
                "error_code": str(error_code or ""),
            },
            payload=payload,
        )
    except Exception as exc:
        raise WorkflowAuditChainError(
            f"Failed to write workflow audit event {event_type}: {exc}",
            error_code="WORKFLOW_AUDIT_WRITE_FAILED",
            context=payload,
        ) from exc

    return {
        "status": "succeeded",
        "entry_id": entry_id,
        "trace_id": normalized_trace_id,
        "session_id": normalized_session_id,
        "task_id": normalized_task_id,
        "node_id": normalized_node_id,
        "node_name": normalized_node_name,
        "evidence_ref": str(evidence_ref or entry_id),
        "event_type": event_type,
    }
