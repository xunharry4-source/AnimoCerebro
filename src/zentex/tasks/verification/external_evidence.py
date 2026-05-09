from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.common.workflow_errors import WorkflowEvidenceError
from zentex.common.workflow_models import WorkflowEvidence


def _base_result(
    *,
    trace_id: str,
    session_id: str,
    task_id: str,
    node_id: str,
    node_name: str,
    evidence_ref: str,
    evidence: dict[str, Any],
) -> WorkflowEvidence:
    return WorkflowEvidence(
        status="succeeded",
        trace_id=trace_id,
        session_id=session_id,
        task_id=task_id,
        node_id=node_id,
        node_name=node_name,
        evidence_ref=evidence_ref,
        evidence=evidence,
    )


def _fail(message: str, *, error_code: str, context: dict[str, Any]) -> None:
    raise WorkflowEvidenceError(message, error_code=error_code, context=context)


def verify_file_exists(path: str | Path, *, require_non_empty: bool = False) -> dict[str, Any]:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        _fail(f"Evidence file does not exist: {file_path}", error_code="EVIDENCE_FILE_MISSING", context={"path": str(file_path)})
    if not file_path.is_file():
        _fail(f"Evidence path is not a file: {file_path}", error_code="EVIDENCE_NOT_FILE", context={"path": str(file_path)})
    size = file_path.stat().st_size
    if require_non_empty and size <= 0:
        _fail(f"Evidence file is empty: {file_path}", error_code="EVIDENCE_FILE_EMPTY", context={"path": str(file_path)})
    return {"path": str(file_path), "size_bytes": size}


def verify_image_header(path: str | Path) -> dict[str, Any]:
    info = verify_file_exists(path, require_non_empty=True)
    file_path = Path(info["path"])
    with file_path.open("rb") as fh:
        header = fh.read(12)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        image_type = "png"
    elif header.startswith(b"\xff\xd8\xff"):
        image_type = "jpeg"
    else:
        _fail(
            f"Evidence image header is not PNG/JPEG: {file_path}",
            error_code="EVIDENCE_IMAGE_HEADER_INVALID",
            context={"path": str(file_path), "header_hex": header.hex()},
        )
    return {**info, "image_type": image_type, "header_hex": header.hex()}


def verify_mongodb_read_after_write(collection: Any, query: dict[str, Any], *, expected_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    if collection is None or not callable(getattr(collection, "find_one", None)):
        _fail("MongoDB collection.find_one is required", error_code="MONGODB_COLLECTION_INVALID", context={})
    document = collection.find_one(dict(query))
    if document is None:
        _fail("MongoDB read-after-write document was not found", error_code="MONGODB_READ_AFTER_WRITE_MISSING", context={"query": query})
    failures = []
    for key, expected in dict(expected_fields or {}).items():
        if document.get(key) != expected:
            failures.append({"field": key, "expected": expected, "actual": document.get(key)})
    if failures:
        _fail(
            "MongoDB read-after-write document did not match expected fields",
            error_code="MONGODB_READ_AFTER_WRITE_MISMATCH",
            context={"query": query, "failures": failures},
        )
    return {"query": query, "document": document, "expected_fields": expected_fields or {}}


def verify_agent_ledger(agent_service: Any, *, external_task_ref: str = "", zentex_task_id: str = "") -> dict[str, Any]:
    if agent_service is None:
        _fail("Agent service is required for ledger verification", error_code="AGENT_SERVICE_MISSING", context={})
    record = None
    if external_task_ref:
        get_invocation = getattr(agent_service, "get_invocation", None) or getattr(
            agent_service,
            "get_invocation_by_external_task_ref",
            None,
        )
        if callable(get_invocation):
            record = get_invocation(external_task_ref)
    if record is None and zentex_task_id:
        list_invocations = getattr(agent_service, "list_task_invocations", None) or getattr(
            agent_service,
            "list_invocations_for_task",
            None,
        )
        if callable(list_invocations):
            invocations = list_invocations(zentex_task_id)
            record = invocations[0] if invocations else None
    if record is None:
        _fail(
            "Agent invocation ledger record was not found",
            error_code="AGENT_LEDGER_RECORD_MISSING",
            context={"external_task_ref": external_task_ref, "zentex_task_id": zentex_task_id},
        )
    payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)
    if external_task_ref and str(payload.get("external_task_ref") or "") != external_task_ref:
        _fail(
            "Agent ledger external_task_ref mismatch",
            error_code="AGENT_LEDGER_EXTERNAL_REF_MISMATCH",
            context={"expected": external_task_ref, "actual": payload.get("external_task_ref"), "record": payload},
        )
    if zentex_task_id and str(payload.get("zentex_task_id") or "") != zentex_task_id:
        _fail(
            "Agent ledger zentex_task_id mismatch",
            error_code="AGENT_LEDGER_TASK_MISMATCH",
            context={"expected": zentex_task_id, "actual": payload.get("zentex_task_id"), "record": payload},
        )
    return {"external_task_ref": external_task_ref or payload.get("external_task_ref"), "record": payload}


def verify_external_side_effect(
    *,
    side_effect_type: str,
    trace_id: str,
    session_id: str,
    task_id: str,
    node_id: str,
    node_name: str,
    evidence_ref: str = "",
    path: str | Path | None = None,
    collection: Any = None,
    query: dict[str, Any] | None = None,
    expected_fields: dict[str, Any] | None = None,
    agent_service: Any = None,
    external_task_ref: str = "",
    audit_service: Any = None,
) -> dict[str, Any]:
    normalized_type = str(side_effect_type or "").strip().lower()
    if normalized_type == "file_exists":
        if path is None:
            _fail("path is required for file_exists side-effect verification", error_code="EVIDENCE_PATH_MISSING", context={})
        evidence = verify_file_exists(path)
    elif normalized_type == "non_empty_file":
        if path is None:
            _fail("path is required for non_empty_file side-effect verification", error_code="EVIDENCE_PATH_MISSING", context={})
        evidence = verify_file_exists(path, require_non_empty=True)
    elif normalized_type in {"image", "screenshot"}:
        if path is None:
            _fail("path is required for image side-effect verification", error_code="EVIDENCE_PATH_MISSING", context={})
        evidence = verify_image_header(path)
    elif normalized_type == "mongodb_read_after_write":
        evidence = verify_mongodb_read_after_write(collection, query or {}, expected_fields=expected_fields)
    elif normalized_type == "agent_ledger":
        evidence = verify_agent_ledger(agent_service, external_task_ref=external_task_ref, zentex_task_id=task_id)
    else:
        _fail(
            f"Unsupported external side-effect type: {side_effect_type}",
            error_code="EVIDENCE_TYPE_UNSUPPORTED",
            context={"side_effect_type": side_effect_type},
        )
    result = _base_result(
        trace_id=trace_id,
        session_id=session_id,
        task_id=task_id,
        node_id=node_id,
        node_name=node_name,
        evidence_ref=evidence_ref or f"{normalized_type}:{task_id}",
        evidence={"side_effect_type": normalized_type, **evidence},
    ).as_dict()
    if audit_service is not None:
        from zentex.audit.workflow_events import record_workflow_node_event

        result["audit"] = record_workflow_node_event(
            audit_service=audit_service,
            event_type="side_effect_verified",
            node_id=node_id,
            node_name=node_name,
            status="succeeded",
            trace_id=trace_id,
            session_id=session_id,
            task_id=task_id,
            output_summary=result["evidence"],
            evidence_ref=result["evidence_ref"],
            source="zentex.tasks.verification.external_evidence",
        )
    return result
