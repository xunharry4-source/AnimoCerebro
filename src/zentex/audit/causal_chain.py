from __future__ import annotations

from typing import Any

from zentex.common.workflow_errors import WorkflowAuditChainError


def _payload(entry: Any) -> dict[str, Any]:
    payload = getattr(entry, "payload", None)
    if isinstance(entry, dict):
        payload = entry.get("payload", entry)
    return payload if isinstance(payload, dict) else {}


def _entry_value(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _event_label(entry: Any) -> str:
    payload = _payload(entry)
    return str(
        payload.get("workflow_event_type")
        or payload.get("event_type")
        or _entry_value(entry, "entry_type")
        or ""
    )


def _node_id(entry: Any) -> str:
    return str(_payload(entry).get("node_id") or "")


def _node_name(entry: Any) -> str:
    return str(_payload(entry).get("node_name") or "")


def _matches(entry: Any, requirement: str | dict[str, Any]) -> bool:
    if isinstance(requirement, str):
        return _event_label(entry) == requirement
    event_type = str(requirement.get("event_type") or requirement.get("workflow_event_type") or "").strip()
    node_id = str(requirement.get("node_id") or "").strip()
    node_name = str(requirement.get("node_name") or "").strip()
    if event_type and _event_label(entry) != event_type:
        return False
    if node_id and _node_id(entry) != node_id:
        return False
    if node_name and _node_name(entry) != node_name:
        return False
    return bool(event_type or node_id or node_name)


def _requirement_label(requirement: str | dict[str, Any]) -> str:
    if isinstance(requirement, str):
        return requirement
    event_type = str(requirement.get("event_type") or requirement.get("workflow_event_type") or "").strip()
    node_id = str(requirement.get("node_id") or "").strip()
    node_name = str(requirement.get("node_name") or "").strip()
    return ":".join(part for part in (event_type, node_id, node_name) if part) or str(requirement)


def _requirement_event_type(requirement: str | dict[str, Any]) -> str:
    if isinstance(requirement, str):
        return requirement
    return str(requirement.get("event_type") or requirement.get("workflow_event_type") or "").strip()


def _requirement_node_id(requirement: str | dict[str, Any]) -> str:
    if isinstance(requirement, str):
        return ""
    return str(requirement.get("node_id") or "").strip()


def _requirement_node_name(requirement: str | dict[str, Any]) -> str:
    if isinstance(requirement, str):
        return ""
    return str(requirement.get("node_name") or "").strip()


def _entry_ref(entry: Any | None) -> dict[str, Any]:
    if entry is None:
        return {}
    return {
        "entry_id": str(_entry_value(entry, "entry_id") or ""),
        "event_type": _event_label(entry),
        "node_id": _node_id(entry),
        "node_name": _node_name(entry),
    }


def _repair_hint(
    *,
    missing_event: str,
    missing_node_id: str,
    missing_node_name: str,
    task_id: str,
    trace_id: str,
) -> str:
    node_part = missing_node_id or missing_node_name or missing_event
    task_part = f" for task {task_id}" if task_id else ""
    return (
        f"Restore or rebuild {missing_event} at {node_part}{task_part} on trace {trace_id}; "
        "then verify the task-outcome-writeback linkage and rerun replay."
    )


def _monitoring_recommendations(*, trace_id: str, task_id: str, status: str) -> list[dict[str, Any]]:
    base_scope = {"trace_id": trace_id, "task_id": task_id}
    return [
        {
            "monitor": "causal_audit_sequence",
            "reason": "detect missing or out-of-order workflow audit events before replay becomes ambiguous",
            "scope": base_scope,
            "repair_hint": "alert on missing required events and rebuild the affected trace segment from source evidence",
        },
        {
            "monitor": "task_outcome_writeback_links",
            "reason": "detect orphan outcomes, memories, learning records, or reflections after task completion",
            "scope": base_scope,
            "repair_hint": "backfill the missing task_id, trace_id, and writeback ids before marking replay complete",
        },
        {
            "monitor": "replay_regression_probe",
            "reason": f"keep replay diagnostics active after causal chain status is {status}",
            "scope": base_scope,
            "repair_hint": "run scheduled replay probes and preserve failed breakpoint reports as audit evidence",
        },
    ]


def _read_trace_entries(audit_service: Any, trace_id: str) -> list[Any]:
    if audit_service is None:
        raise WorkflowAuditChainError(
            "audit_service is required for causal audit chain verification",
            error_code="WORKFLOW_AUDIT_SERVICE_MISSING",
        )
    for method_name in ("list_trace_events", "read_by_trace_id"):
        method = getattr(audit_service, method_name, None)
        if callable(method):
            return list(method(trace_id) or [])
    store = getattr(audit_service, "store", None)
    method = getattr(store, "read_by_trace_id", None)
    if callable(method):
        return list(method(trace_id) or [])
    raise WorkflowAuditChainError(
        "audit_service must expose list_trace_events(trace_id) or read_by_trace_id(trace_id)",
        error_code="WORKFLOW_AUDIT_READER_MISSING",
    )


def build_causal_audit_chain_report(
    *,
    audit_service: Any,
    trace_id: str,
    required_audit_events: list[str | dict[str, Any]],
    session_id: str = "",
    task_id: str = "",
    require_order: bool = True,
) -> dict[str, Any]:
    normalized_trace_id = str(trace_id or "").strip()
    if not normalized_trace_id:
        raise WorkflowAuditChainError("trace_id is required", error_code="WORKFLOW_TRACE_ID_MISSING")

    entries = _read_trace_entries(audit_service, normalized_trace_id)
    failures: list[dict[str, Any]] = []
    matched_indexes: list[int] = []
    search_start = 0

    for requirement in required_audit_events:
        match_index = -1
        iterable = enumerate(entries[search_start:], start=search_start) if require_order else enumerate(entries)
        for index, entry in iterable:
            if _matches(entry, requirement):
                match_index = index
                break
        if match_index < 0:
            previous_entry = entries[search_start - 1] if search_start > 0 and entries else None
            next_entry = entries[search_start] if search_start < len(entries) else None
            missing_event = _requirement_event_type(requirement) or _requirement_label(requirement)
            missing_node_id = _requirement_node_id(requirement)
            missing_node_name = _requirement_node_name(requirement)
            failures.append(
                {
                    "reason": "causal_audit_break",
                    "error_code": "CAUSAL_AUDIT_BREAK",
                    "missing_event": missing_event,
                    "missing_node_id": missing_node_id,
                    "missing_node_name": missing_node_name,
                    "previous_event": _entry_ref(previous_entry),
                    "next_event": _entry_ref(next_entry),
                    "trace_id": normalized_trace_id,
                    "session_id": session_id,
                    "affected_task_id": task_id,
                    "repair_hint": _repair_hint(
                        missing_event=missing_event,
                        missing_node_id=missing_node_id,
                        missing_node_name=missing_node_name,
                        task_id=task_id,
                        trace_id=normalized_trace_id,
                    ),
                }
            )
            continue
        matched_indexes.append(match_index)
        if require_order:
            search_start = match_index + 1

    status = "succeeded" if not failures else "failed"
    breakpoints = list(failures)
    first_failure = failures[0] if failures else {}
    return {
        "status": status,
        "error_code": "" if status == "succeeded" else "CAUSAL_AUDIT_BREAK",
        "missing_event": first_failure.get("missing_event", ""),
        "missing_node_id": first_failure.get("missing_node_id", ""),
        "previous_event": first_failure.get("previous_event", {}),
        "next_event": first_failure.get("next_event", {}),
        "affected_task_id": first_failure.get("affected_task_id", ""),
        "repair_hint": first_failure.get("repair_hint", ""),
        "trace_id": normalized_trace_id,
        "session_id": session_id,
        "task_id": task_id,
        "node_id": "audit-chain",
        "node_name": "Causal Audit Chain",
        "evidence_ref": f"audit_trace:{normalized_trace_id}",
        "checked_event_count": len(entries),
        "matched_event_indexes": matched_indexes,
        "required_audit_events": [_requirement_label(item) for item in required_audit_events],
        "failures": failures,
        "breakpoints": breakpoints,
        "monitoring_recommendations": _monitoring_recommendations(
            trace_id=normalized_trace_id,
            task_id=task_id,
            status=status,
        ),
    }
