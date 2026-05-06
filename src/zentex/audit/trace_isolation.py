from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _metadata(task: Any) -> dict[str, Any]:
    if isinstance(task, dict):
        return task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    metadata = getattr(task, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _payload(entry: Any) -> dict[str, Any]:
    if isinstance(entry, dict):
        payload = entry.get("payload", entry)
    else:
        payload = getattr(entry, "payload", None)
    return payload if isinstance(payload, dict) else {}


def verify_trace_isolation(
    *,
    task_service: Any = None,
    audit_service: Any = None,
    session_id: str,
    trace_id: str,
    task_ids: list[str] | None = None,
    writeback_records: list[Any] | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    checked_tasks = []
    for task_id in list(task_ids or []):
        if task_service is None or not callable(getattr(task_service, "get_task", None)):
            failures.append({"reason": "task_service_missing", "error_code": "TASK_SERVICE_QUERY_METHOD_MISSING"})
            break
        task = task_service.get_task(task_id)
        metadata = _metadata(task)
        checked_tasks.append(task_id)
        if metadata.get("session_id") != session_id:
            failures.append({"reason": "task_session_pollution", "task_id": task_id, "expected": session_id, "actual": metadata.get("session_id")})
        task_trace = str(metadata.get("trace_id") or "")
        if task_trace and task_trace != trace_id:
            failures.append({"reason": "task_trace_pollution", "task_id": task_id, "expected": trace_id, "actual": task_trace})

    checked_audit_events = 0
    if audit_service is not None:
        reader = getattr(audit_service, "list_trace_events", None)
        if not callable(reader) and getattr(audit_service, "store", None) is not None:
            reader = getattr(audit_service.store, "read_by_trace_id", None)
        if callable(reader):
            for entry in list(reader(trace_id) or []):
                checked_audit_events += 1
                entry_session = str(getattr(entry, "session_id", "") or _payload(entry).get("session_id") or "")
                if entry_session and entry_session != session_id:
                    failures.append(
                        {
                            "reason": "audit_session_pollution",
                            "error_code": "TRACE_ISOLATION_VIOLATION",
                            "entry_id": str(getattr(entry, "entry_id", "") or ""),
                            "expected": session_id,
                            "actual": entry_session,
                        }
                    )
        else:
            failures.append({"reason": "audit_reader_missing", "error_code": "WORKFLOW_AUDIT_READER_MISSING"})

    checked_writebacks = 0
    for record in list(writeback_records or []):
        checked_writebacks += 1
        payload = _as_dict(record)
        record_session = str(payload.get("session_id") or payload.get("context", {}).get("session_id") or "")
        record_trace = str(payload.get("trace_id") or payload.get("context", {}).get("trace_id") or "")
        if record_session and record_session != session_id:
            failures.append({"reason": "writeback_session_pollution", "expected": session_id, "actual": record_session})
        if record_trace and record_trace != trace_id:
            failures.append({"reason": "writeback_trace_pollution", "expected": trace_id, "actual": record_trace})

    status = "succeeded" if not failures else "failed"
    return {
        "status": status,
        "error_code": "" if status == "succeeded" else "TRACE_ISOLATION_VIOLATION",
        "trace_id": trace_id,
        "session_id": session_id,
        "task_id": "",
        "node_id": "isolation",
        "node_name": "Trace Isolation",
        "evidence_ref": f"trace_isolation:{session_id}:{trace_id}",
        "evidence": {
            "checked_tasks": checked_tasks,
            "checked_audit_events": checked_audit_events,
            "checked_writebacks": checked_writebacks,
        },
        "failures": failures,
    }

