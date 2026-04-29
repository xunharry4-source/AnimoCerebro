from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.governance.architecture_redline_matrix import (
    ArchitectureRedlineValidationRequest,
    ArchitectureRedlineValidationReport,
    architecture_redline_matrix,
    evaluate_architecture_redlines,
    report_to_audit_payload,
)
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType


router = APIRouter(prefix="/architecture-redlines", tags=["architecture-redlines"])


def _audit_store(request: Request) -> Any:
    return getattr(request.app.state, "transcript_store", None)


def _write_audit(request: Request, report: ArchitectureRedlineValidationReport) -> None:
    store = _audit_store(request)
    if store is None or not callable(getattr(store, "write_entry", None)):
        raise RuntimeError("BrainTranscriptStore is unavailable for architecture redline audit")
    store.write_entry(
        session_id="architecture-redline",
        turn_id=report.validation_id,
        entry_type=BrainTranscriptEntryType.FLOW_AUDIT,
        timestamp=datetime.fromisoformat(report.evaluated_at),
        source="architecture.redline.matrix",
        trace_id=report.trace_id,
        payload=report_to_audit_payload(report),
    )


@router.get("/matrix")
def get_architecture_redline_matrix() -> dict[str, Any]:
    return architecture_redline_matrix()


@router.post("/evaluate")
def evaluate_architecture_redline_request(
    payload: ArchitectureRedlineValidationRequest,
    request: Request,
) -> ArchitectureRedlineValidationReport:
    report = evaluate_architecture_redlines(payload)
    _write_audit(request, report)
    return report


@router.post("/enforce")
def enforce_architecture_redline_request(
    payload: ArchitectureRedlineValidationRequest,
    request: Request,
) -> ArchitectureRedlineValidationReport:
    report = evaluate_architecture_redlines(payload)
    _write_audit(request, report)
    if not report.allowed:
        raise HTTPException(status_code=409, detail=report.model_dump(mode="json"))
    return report


@router.get("/audit")
def list_architecture_redline_audit(request: Request, limit: int = 100) -> dict[str, Any]:
    store = _audit_store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="BrainTranscriptStore is unavailable")
    if callable(getattr(store, "list_entries", None)):
        entries = list(store.list_entries(entry_type="architecture_redline_validation", limit=limit) or [])
    elif callable(getattr(store, "read_entries", None)):
        entries = list(store.read_entries() or [])
    else:
        raise HTTPException(status_code=503, detail="BrainTranscriptStore query API is unavailable")
    rows: list[dict[str, Any]] = []
    for entry in entries:
        payload = entry.get("payload", {}) if isinstance(entry, dict) else getattr(entry, "payload", {})
        if not isinstance(payload, dict):
            continue
        if payload.get("event_type") != "architecture_redline_validation":
            continue
        rows.append(payload)
    return {"items": rows[-limit:], "count": len(rows[-limit:])}
