from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from zentex.governance.unified_errors import (
    RawErrorInput,
    UnifiedErrorReport,
    map_raw_error,
    unified_error_catalog,
    unified_error_statistics,
)


router = APIRouter(tags=["unified-errors"])


def _store(request: Request) -> dict[str, dict[str, Any]]:
    current = getattr(request.app.state, "unified_error_reports", None)
    if current is None:
        current = {}
        request.app.state.unified_error_reports = current
    return current


def _audit(request: Request, report: UnifiedErrorReport) -> None:
    transcript_store = getattr(request.app.state, "transcript_store", None)
    if transcript_store is None or not callable(getattr(transcript_store, "write_entry", None)):
        return
    error = report.unified_error
    transcript_store.write_entry(
        session_id="unified-errors",
        turn_id=error.error_id,
        entry_type="error_audit_event",
        payload=report.audit_payload,
        source="governance.unified_errors",
        trace_id=error.trace_id,
    )


@router.get("/unified-errors/catalog")
def get_unified_error_catalog() -> dict[str, Any]:
    return unified_error_catalog()


@router.post("/unified-errors")
def create_unified_error(payload: RawErrorInput, request: Request) -> dict[str, Any]:
    report = map_raw_error(payload)
    _store(request)[report.unified_error.error_id] = report.model_dump(mode="json")
    _audit(request, report)
    return report.model_dump(mode="json")


@router.get("/unified-errors")
def list_unified_errors(
    request: Request,
    trace_id: str | None = Query(default=None),
    module: str | None = Query(default=None),
    category: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    action: str | None = Query(default=None),
    retryable: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    reports = list(_store(request).values())
    if trace_id:
        reports = [item for item in reports if item["unified_error"]["trace_id"] == trace_id]
    if module:
        reports = [item for item in reports if item["unified_error"]["source_module"] == module]
    if category:
        reports = [item for item in reports if item["unified_error"]["error_category"] == category]
    if stage:
        reports = [item for item in reports if item["unified_error"]["error_stage"] == stage]
    if action:
        reports = [item for item in reports if item["disposition"]["action"] == action]
    if retryable is not None:
        reports = [item for item in reports if item["unified_error"]["retryable"] is retryable]
    sorted_reports = sorted(reports, key=lambda item: item["unified_error"]["occurred_at"], reverse=True)
    return sorted_reports[offset: offset + limit]


@router.get("/unified-errors/statistics")
def get_unified_error_statistics(
    request: Request,
    trace_id: str | None = Query(default=None),
) -> dict[str, Any]:
    reports = list(_store(request).values())
    if trace_id:
        reports = [item for item in reports if item["unified_error"]["trace_id"] == trace_id]
    return unified_error_statistics(reports)


@router.get("/unified-errors/{error_id}")
def get_unified_error(error_id: str, request: Request) -> dict[str, Any]:
    report = _store(request).get(error_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"unified error not found: {error_id}")
    return report
