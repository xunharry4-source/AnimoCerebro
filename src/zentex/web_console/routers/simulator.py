"""Web API for G33 controlled environment simulator."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.safety.environment_simulator import EnvironmentFaultSimulator, FaultInjectionRequest

router = APIRouter(prefix="/simulator", tags=["simulator"])


def _simulator(request: Request) -> EnvironmentFaultSimulator:
    simulator = getattr(request.app.state, "environment_fault_simulator", None)
    if simulator is None:
        simulator = EnvironmentFaultSimulator()
        request.app.state.environment_fault_simulator = simulator
    return simulator


@router.get("/templates")
def list_templates(request: Request) -> list[dict[str, Any]]:
    """Return the controlled fault template catalog."""

    return [row.model_dump(mode="json") for row in _simulator(request).list_templates()]


@router.post("/inject")
def inject_fault(payload: FaultInjectionRequest, request: Request) -> dict[str, Any]:
    """Inject a controlled simulator fault and return its report."""

    try:
        record, report = _simulator(request).inject(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "template_not_found", "message": str(exc)}) from exc
    return {"injection": record.model_dump(mode="json"), "report": report.model_dump(mode="json")}


@router.post("/rollback/{injection_id}")
def rollback_fault(injection_id: str, request: Request) -> dict[str, Any]:
    """Rollback a controlled fault injection."""

    try:
        record = _simulator(request).rollback(injection_id)
        report = _simulator(request).get_report(injection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "injection_not_found", "message": str(exc)}) from exc
    return {"injection": record.model_dump(mode="json"), "report": report.model_dump(mode="json")}


@router.get("/report")
def get_report(injection_id: str, request: Request) -> dict[str, Any]:
    """Return a structured drill report by injection id."""

    try:
        return _simulator(request).get_report(injection_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "report_not_found", "message": str(exc)}) from exc


@router.get("/injections")
def list_injections(request: Request) -> list[dict[str, Any]]:
    """Return all simulator injection records."""

    return [row.model_dump(mode="json") for row in _simulator(request).list_injections()]


@router.get("/injections/{injection_id}")
def get_injection(injection_id: str, request: Request) -> dict[str, Any]:
    """Return one simulator injection record."""

    try:
        return _simulator(request).get_injection(injection_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "injection_not_found", "message": str(exc)}) from exc


@router.get("/audit")
def list_audit(request: Request) -> list[dict[str, Any]]:
    """Return simulator audit events."""

    return [row.model_dump(mode="json") for row in _simulator(request).list_audit_events()]
