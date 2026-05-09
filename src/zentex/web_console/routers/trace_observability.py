from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from zentex.governance.trace_observability import (
    TraceObservationReport,
    TraceObservationRequest,
    evaluate_trace_observability,
    trace_observability_requirements,
)


router = APIRouter(tags=["trace-observability"])


def _store(request: Request) -> dict[str, dict[str, Any]]:
    current = getattr(request.app.state, "trace_observability_reports", None)
    if current is None:
        current = {}
        request.app.state.trace_observability_reports = current
    return current


def _audit(request: Request, report: TraceObservationReport) -> None:
    transcript_store = getattr(request.app.state, "transcript_store", None)
    if transcript_store is None or not callable(getattr(transcript_store, "write_entry", None)):
        return
    transcript_store.write_entry(
        session_id="trace-observability",
        turn_id=report.observation_id,
        entry_type="observability_audit_event",
        payload={
            "event": "trace_observability_evaluated",
            "observation_id": report.observation_id,
            "request_id": report.request_id,
            "trace_id": report.trace_id,
            "observability_status": report.observability_status,
            "span_count": report.span_count,
            "critical_anomaly_count": report.metrics["trace_integrity_metrics"]["critical_anomaly_count"],
            "searchable_refs": report.searchable_refs,
        },
        source="governance.trace_observability",
        trace_id=report.trace_id,
    )


@router.get("/trace-observability/requirements")
def get_trace_observability_requirements() -> dict[str, Any]:
    return trace_observability_requirements()


@router.post("/trace-observability/traces")
def create_trace_observability_report(
    payload: TraceObservationRequest,
    request: Request,
) -> dict[str, Any]:
    report = evaluate_trace_observability(payload)
    _store(request)[report.observation_id] = report.model_dump(mode="json")
    _audit(request, report)
    return report.model_dump(mode="json")


@router.get("/trace-observability/traces/{observation_id}")
def get_trace_observability_report(observation_id: str, request: Request) -> dict[str, Any]:
    report = _store(request).get(observation_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"trace observability report not found: {observation_id}")
    return report


@router.get("/trace-observability/traces")
def list_trace_observability_reports(
    request: Request,
    trace_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    decision_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    reports = list(_store(request).values())
    if trace_id:
        reports = [item for item in reports if item["trace_id"] == trace_id]
    if request_id:
        reports = [
            item
            for item in reports
            if item["request_id"] == request_id or request_id in item["searchable_refs"].get("request_ids", [])
        ]
    if task_id:
        reports = [item for item in reports if task_id in item["searchable_refs"].get("task_ids", [])]
    if agent_id:
        reports = [item for item in reports if agent_id in item["searchable_refs"].get("agent_ids", [])]
    if decision_id:
        reports = [item for item in reports if decision_id in item["searchable_refs"].get("decision_ids", [])]
    return sorted(reports, key=lambda item: item["observed_at"], reverse=True)
