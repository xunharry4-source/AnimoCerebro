from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from zentex.safety.cloud_auditor import (
    CloudAuditDecision,
    CloudAuditorClient,
    CloudBoundaryDefinition,
    DegradationRecord,
)


router = APIRouter()


class CloudAuditorConfigureRequest(BaseModel):
    endpoint: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    timeout_seconds: float | None = Field(default=None, ge=1.0)


class CloudAuditActionRequest(BaseModel):
    action_type: str = Field(min_length=1)
    action_payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    context: dict[str, Any] = Field(default_factory=dict)
    use_cache: bool = True


def _get_client(request: Request) -> CloudAuditorClient:
    client = getattr(request.app.state, "cloud_sanity_auditor_client", None)
    if client is not None:
        return client
    client = CloudAuditorClient()
    request.app.state.cloud_sanity_auditor_client = client
    return client


@router.get("/cloud-sanity-auditor/boundary")
def get_boundary(request: Request) -> CloudBoundaryDefinition:
    return _get_client(request).get_boundary_definition()


@router.post("/cloud-sanity-auditor/config")
def configure_cloud_auditor(payload: CloudAuditorConfigureRequest, request: Request) -> dict[str, Any]:
    client = _get_client(request)
    client.configure(
        endpoint=payload.endpoint,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        timeout_seconds=payload.timeout_seconds,
    )
    return {
        "status": "configured" if client.is_configured else "missing_credentials",
        "is_configured": client.is_configured,
    }


@router.post("/cloud-sanity-auditor/audit-actions")
def audit_action(payload: CloudAuditActionRequest, request: Request) -> CloudAuditDecision:
    return _get_client(request).audit_action(
        payload.action_type,
        payload.action_payload,
        risk_level=payload.risk_level,
        context=payload.context,
        use_cache=payload.use_cache,
    )


@router.get("/cloud-sanity-auditor/decisions")
def list_decisions(request: Request) -> list[CloudAuditDecision]:
    return _get_client(request).get_decision_history()


@router.get("/cloud-sanity-auditor/decisions/{decision_id}")
def get_decision(decision_id: str, request: Request) -> CloudAuditDecision:
    decision = _get_client(request).get_decision(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"CloudAuditDecision {decision_id} not found")
    return decision


@router.get("/cloud-sanity-auditor/degradations")
def list_degradations(request: Request) -> list[DegradationRecord]:
    return _get_client(request).get_degradation_history()


@router.get("/cloud-sanity-auditor/requests")
def list_requests(request: Request) -> list[Any]:
    return _get_client(request).get_request_history()
