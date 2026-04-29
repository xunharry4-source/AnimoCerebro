from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.governance.management_acceptance import (
    ManagementAcceptanceReport,
    ManagementAcceptanceRequest,
    evaluate_management_acceptance,
    management_acceptance_matrix,
)


router = APIRouter(tags=["management-acceptance"])


def _store(request: Request) -> dict[str, dict[str, Any]]:
    current = getattr(request.app.state, "management_acceptance_reports", None)
    if current is None:
        current = {}
        request.app.state.management_acceptance_reports = current
    return current


def _audit(request: Request, report: ManagementAcceptanceReport) -> None:
    transcript_store = getattr(request.app.state, "transcript_store", None)
    if transcript_store is None or not callable(getattr(transcript_store, "write_entry", None)):
        return
    transcript_store.write_entry(
        session_id="management-acceptance",
        turn_id=report.evaluation_id,
        entry_type="plugin_audit_event",
        payload={
            "event": "management_acceptance_evaluated",
            "evaluation_id": report.evaluation_id,
            "request_id": report.request_id,
            "release_candidate": report.release_candidate,
            "release_decision": report.release_decision,
            "blocker_count": len(report.blockers),
            "completion_summary": report.completion_summary,
        },
        source="governance.management_acceptance",
        trace_id=report.evaluation_id,
    )


@router.get("/management-acceptance/matrix")
def get_management_acceptance_matrix() -> dict[str, Any]:
    return management_acceptance_matrix()


@router.post("/management-acceptance/evaluations")
def create_management_acceptance_evaluation(
    payload: ManagementAcceptanceRequest,
    request: Request,
) -> dict[str, Any]:
    report = evaluate_management_acceptance(payload)
    _store(request)[report.evaluation_id] = report.model_dump(mode="json")
    _audit(request, report)
    return report.model_dump(mode="json")


@router.get("/management-acceptance/evaluations/{evaluation_id}")
def get_management_acceptance_evaluation(evaluation_id: str, request: Request) -> dict[str, Any]:
    report = _store(request).get(evaluation_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"management acceptance evaluation not found: {evaluation_id}")
    return report


@router.get("/management-acceptance/evaluations")
def list_management_acceptance_evaluations(request: Request) -> list[dict[str, Any]]:
    return sorted(_store(request).values(), key=lambda item: item["evaluated_at"], reverse=True)
