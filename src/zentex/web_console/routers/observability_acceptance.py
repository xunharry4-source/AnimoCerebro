from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.governance.observability_acceptance import (
    ObservabilityAcceptanceReport,
    ObservabilityAcceptanceRequest,
    evaluate_observability_acceptance,
    observability_acceptance_matrix,
)


router = APIRouter(tags=["observability-acceptance"])


def _evaluations(request: Request) -> dict[str, dict[str, Any]]:
    current = getattr(request.app.state, "observability_acceptance_reports", None)
    if current is None:
        current = {}
        request.app.state.observability_acceptance_reports = current
    return current


def _reports(request: Request, attr_name: str) -> list[dict[str, Any]]:
    current = getattr(request.app.state, attr_name, None)
    if current is None:
        return []
    if isinstance(current, dict):
        return list(current.values())
    return list(current)


def _audit_events(request: Request) -> list[dict[str, Any]]:
    transcript_store = getattr(request.app.state, "transcript_store", None)
    if transcript_store is None:
        return []
    entries = []
    if callable(getattr(transcript_store, "list_entries", None)):
        entries = transcript_store.list_entries()
    elif hasattr(transcript_store, "entries"):
        entries = list(transcript_store.entries)
    payloads: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict):
            payload = entry.get("payload")
        else:
            payload = getattr(entry, "payload", None)
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _write_audit(request: Request, report: ObservabilityAcceptanceReport) -> None:
    transcript_store = getattr(request.app.state, "transcript_store", None)
    if transcript_store is None or not callable(getattr(transcript_store, "write_entry", None)):
        return
    transcript_store.write_entry(
        session_id="observability-acceptance",
        turn_id=report.evaluation_id,
        entry_type="governance_audit_event",
        payload={
            "event": "observability_acceptance_evaluated",
            "evaluation_id": report.evaluation_id,
            "request_id": report.request_id,
            "release_candidate": report.release_candidate,
            "release_decision": report.release_decision,
            "real_complete": report.real_complete,
            "blocker_count": len(report.blockers),
            "completion_summary": report.completion_summary,
        },
        source="governance.observability_acceptance",
        trace_id=report.evaluation_id,
    )


@router.get("/observability-acceptance/matrix")
def get_observability_acceptance_matrix() -> dict[str, Any]:
    return observability_acceptance_matrix()


@router.post("/observability-acceptance/evaluations")
def create_observability_acceptance_evaluation(
    payload: ObservabilityAcceptanceRequest,
    request: Request,
) -> dict[str, Any]:
    report = evaluate_observability_acceptance(
        payload,
        observation_reports=_reports(request, "trace_observability_reports"),
        replay_reports=_reports(request, "trace_replay_reports"),
        unified_error_reports=_reports(request, "unified_error_reports"),
        audit_events=_audit_events(request),
    )
    _evaluations(request)[report.evaluation_id] = report.model_dump(mode="json")
    _write_audit(request, report)
    return report.model_dump(mode="json")


@router.get("/observability-acceptance/evaluations")
def list_observability_acceptance_evaluations(request: Request) -> list[dict[str, Any]]:
    return sorted(_evaluations(request).values(), key=lambda item: item["evaluated_at"], reverse=True)


@router.get("/observability-acceptance/evaluations/{evaluation_id}")
def get_observability_acceptance_evaluation(evaluation_id: str, request: Request) -> dict[str, Any]:
    report = _evaluations(request).get(evaluation_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"observability acceptance evaluation not found: {evaluation_id}")
    return report
