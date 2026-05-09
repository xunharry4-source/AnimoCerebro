from __future__ import annotations

from typing import Any

from zentex.common.workflow_errors import WorkflowWritebackError
from zentex.common.workflow_models import WritebackEvidence


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _record_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(_as_dict(value) or value)


def _missing_terms(value: Any, terms: list[str]) -> list[str]:
    text = _record_text(value).lower()
    return [term for term in terms if term and term.lower() not in text]


def _verify_memory(memory_service: Any, *, task_id: str, memory_id: str, required_terms: list[str]) -> dict[str, Any]:
    if not memory_id:
        raise WorkflowWritebackError("memory_id is required", error_code="MEMORY_ID_MISSING")
    if memory_service is None or not callable(getattr(memory_service, "get_record", None)):
        raise WorkflowWritebackError("memory_service.get_record is required", error_code="MEMORY_SERVICE_INVALID")
    record = memory_service.get_record(memory_id)
    payload = _as_dict(getattr(record, "payload", None))
    if getattr(record, "target_id", None) != task_id and payload.get("task_id") != task_id:
        raise WorkflowWritebackError(
            "Memory writeback does not belong to task",
            error_code="WRITEBACK_TASK_MISMATCH",
            context={"task_id": task_id, "memory_id": memory_id},
        )
    missing_terms = _missing_terms(record, required_terms)
    if missing_terms:
        raise WorkflowWritebackError(
            "Memory writeback content does not contain required workflow context",
            error_code="WRITEBACK_CONTENT_INVALID",
            context={"memory_id": memory_id, "missing_terms": missing_terms},
        )
    return {"memory_id": memory_id, "record": _as_dict(record) or {"payload": payload}}


def _verify_learning(learning_service: Any, *, task_id: str, learning_trace_id: str, required_terms: list[str]) -> dict[str, Any]:
    if not learning_trace_id:
        raise WorkflowWritebackError("learning_trace_id is required", error_code="LEARNING_TRACE_ID_MISSING")
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise WorkflowWritebackError("learning_service.query_overall_records is required", error_code="LEARNING_SERVICE_INVALID")
    records = list(learning_service.query_overall_records(limit=50, trace_id=learning_trace_id) or [])
    matching = []
    for record in records:
        detail = _as_dict(getattr(record, "detail", None))
        if detail.get("task_id") == task_id:
            matching.append(record)
    if not matching:
        raise WorkflowWritebackError(
            "Learning writeback does not belong to task",
            error_code="WRITEBACK_TASK_MISMATCH",
            context={"task_id": task_id, "learning_trace_id": learning_trace_id},
        )
    reusable_records = []
    for record in matching:
        detail = _as_dict(getattr(record, "detail", None))
        if detail.get("best_practice") or detail.get("avoid_pattern"):
            reusable_records.append(record)
    if not reusable_records:
        raise WorkflowWritebackError(
            "Learning writeback does not contain best_practice or avoid_pattern evidence",
            error_code="WRITEBACK_CONTENT_INVALID",
            context={"learning_trace_id": learning_trace_id},
        )
    missing_by_record = [_missing_terms(record, required_terms) for record in reusable_records]
    if required_terms and not any(not missing for missing in missing_by_record):
        raise WorkflowWritebackError(
            "Learning writeback content does not contain required workflow context",
            error_code="WRITEBACK_CONTENT_INVALID",
            context={"learning_trace_id": learning_trace_id, "missing_terms_by_record": missing_by_record},
        )
    return {
        "learning_trace_id": learning_trace_id,
        "records": [_as_dict(record) or {"detail": _as_dict(getattr(record, "detail", None))} for record in matching],
    }


def _verify_reflection(reflection_service: Any, *, task_id: str, reflection_id: str, required_terms: list[str]) -> dict[str, Any]:
    if not reflection_id:
        raise WorkflowWritebackError("reflection_id is required", error_code="REFLECTION_ID_MISSING")
    if reflection_service is None or not callable(getattr(reflection_service, "get_reflection", None)):
        raise WorkflowWritebackError("reflection_service.get_reflection is required", error_code="REFLECTION_SERVICE_INVALID")
    record = reflection_service.get_reflection(reflection_id)
    context = _as_dict(getattr(record, "context", None))
    if context.get("task_id") != task_id:
        raise WorkflowWritebackError(
            "Reflection writeback does not belong to task",
            error_code="WRITEBACK_TASK_MISMATCH",
            context={"task_id": task_id, "reflection_id": reflection_id},
        )
    if not (context.get("root_cause") or context.get("actionable_adjustment")):
        raise WorkflowWritebackError(
            "Reflection writeback does not contain root_cause or actionable_adjustment evidence",
            error_code="WRITEBACK_CONTENT_INVALID",
            context={"reflection_id": reflection_id},
        )
    missing_terms = _missing_terms(record, required_terms)
    if missing_terms:
        raise WorkflowWritebackError(
            "Reflection writeback content does not contain required workflow context",
            error_code="WRITEBACK_CONTENT_INVALID",
            context={"reflection_id": reflection_id, "missing_terms": missing_terms},
        )
    return {"reflection_id": reflection_id, "record": _as_dict(record) or {"context": context}}


def verify_writeback_content(
    *,
    task_id: str,
    trace_id: str,
    session_id: str,
    node_id: str,
    node_name: str,
    memory_service: Any = None,
    memory_id: str = "",
    learning_service: Any = None,
    learning_trace_id: str = "",
    reflection_service: Any = None,
    reflection_id: str = "",
    required_memory_terms: list[str] | None = None,
    required_learning_terms: list[str] | None = None,
    required_reflection_terms: list[str] | None = None,
    audit_service: Any = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    memory_verified = learning_verified = reflection_verified = False
    if memory_id:
        evidence["memory"] = _verify_memory(
            memory_service,
            task_id=task_id,
            memory_id=memory_id,
            required_terms=list(required_memory_terms or []),
        )
        memory_verified = True
    if learning_trace_id:
        evidence["learning"] = _verify_learning(
            learning_service,
            task_id=task_id,
            learning_trace_id=learning_trace_id,
            required_terms=list(required_learning_terms or []),
        )
        learning_verified = True
    if reflection_id:
        evidence["reflection"] = _verify_reflection(
            reflection_service,
            task_id=task_id,
            reflection_id=reflection_id,
            required_terms=list(required_reflection_terms or []),
        )
        reflection_verified = True
    if not any((memory_verified, learning_verified, reflection_verified)):
        raise WorkflowWritebackError("At least one writeback id is required", error_code="WRITEBACK_ID_MISSING")
    result = WritebackEvidence(
        status="succeeded",
        trace_id=trace_id,
        session_id=session_id,
        task_id=task_id,
        node_id=node_id,
        node_name=node_name,
        evidence_ref=f"writeback:{task_id}",
        evidence=evidence,
        memory_verified=memory_verified,
        learning_verified=learning_verified,
        reflection_verified=reflection_verified,
    ).as_dict()
    if audit_service is not None:
        from zentex.audit.workflow_events import record_workflow_node_event

        result["audit"] = record_workflow_node_event(
            audit_service=audit_service,
            event_type="writeback_verified",
            node_id=node_id,
            node_name=node_name,
            status="succeeded",
            trace_id=trace_id,
            session_id=session_id,
            task_id=task_id,
            output_summary={
                "memory_verified": memory_verified,
                "learning_verified": learning_verified,
                "reflection_verified": reflection_verified,
            },
            evidence_ref=f"writeback:{task_id}",
            source="zentex.tasks.verification.writebacks",
        )
    return result
