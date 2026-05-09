from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from zentex.governance.trace_replay import (
    TraceReplayBuildRequest,
    TraceReplayReport,
    build_trace_replay_report,
    trace_replay_capabilities,
)


router = APIRouter(tags=["trace-replay"])


def _observation_reports(request: Request) -> dict[str, dict[str, Any]]:
    current = getattr(request.app.state, "trace_observability_reports", None)
    if current is None:
        current = {}
        request.app.state.trace_observability_reports = current
    return current


def _replay_reports(request: Request) -> dict[str, dict[str, Any]]:
    current = getattr(request.app.state, "trace_replay_reports", None)
    if current is None:
        current = {}
        request.app.state.trace_replay_reports = current
    return current


def _find_observation_by_trace_id(request: Request, trace_id: str) -> dict[str, Any]:
    reports = [
        item
        for item in _observation_reports(request).values()
        if item.get("trace_id") == trace_id
    ]
    if not reports:
        raise HTTPException(status_code=404, detail=f"trace observability source not found: {trace_id}")
    return sorted(reports, key=lambda item: item["observed_at"], reverse=True)[0]


def _audit(request: Request, report: TraceReplayReport) -> None:
    transcript_store = getattr(request.app.state, "transcript_store", None)
    if transcript_store is None or not callable(getattr(transcript_store, "write_entry", None)):
        return
    transcript_store.write_entry(
        session_id="trace-replay",
        turn_id=report.replay_id,
        entry_type="replay_audit_event",
        payload={
            "event": "trace_replay_built",
            "replay_id": report.replay_id,
            "trace_id": report.trace_id,
            "source_observation_id": report.source_observation_id,
            "mode": report.mode,
            "reconstruction_status": report.reconstruction_status,
            "production_side_effects_enabled": report.production_side_effects_enabled,
            "warning_count": len(report.warnings),
            "root_cause": report.postmortem_report.get("root_cause"),
        },
        source="governance.trace_replay",
        trace_id=report.trace_id,
    )


@router.get("/trace-replay/capabilities")
def get_trace_replay_capabilities() -> dict[str, Any]:
    return trace_replay_capabilities()


@router.post("/trace-replay/replays")
def create_trace_replay(payload: TraceReplayBuildRequest, request: Request) -> dict[str, Any]:
    observation = _find_observation_by_trace_id(request, payload.trace_id)
    compare_observation = (
        _find_observation_by_trace_id(request, payload.compare_trace_id)
        if payload.compare_trace_id
        else None
    )
    try:
        report = build_trace_replay_report(
            observation,
            payload,
            compare_observation_report=compare_observation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _replay_reports(request)[report.replay_id] = report.model_dump(mode="json")
    _audit(request, report)
    return report.model_dump(mode="json")


@router.get("/trace-replay/replays/{replay_id}")
def get_trace_replay(replay_id: str, request: Request) -> dict[str, Any]:
    report = _replay_reports(request).get(replay_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"trace replay report not found: {replay_id}")
    return report


@router.get("/trace-replay/replays")
def list_trace_replays(
    request: Request,
    trace_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    decision_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    reports = list(_replay_reports(request).values())
    if trace_id:
        reports = [item for item in reports if item["trace_id"] == trace_id]
    if request_id:
        reports = [item for item in reports if request_id in item["searchable_refs"].get("request_ids", [])]
    if task_id:
        reports = [item for item in reports if task_id in item["searchable_refs"].get("task_ids", [])]
    if agent_id:
        reports = [item for item in reports if agent_id in item["searchable_refs"].get("agent_ids", [])]
    if decision_id:
        reports = [item for item in reports if decision_id in item["searchable_refs"].get("decision_ids", [])]
    return sorted(reports, key=lambda item: item["replayed_at"], reverse=True)
