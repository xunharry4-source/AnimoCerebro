from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from zentex.safety.sanity_auditor import AuditCheckpoint, SanityAuditReport, SanityAuditor


router = APIRouter()


class SanityAuditRequest(BaseModel):
    world_model: dict[str, Any] = Field(default_factory=dict)
    strategy_graph: dict[str, Any] = Field(default_factory=dict)
    ban_layer: dict[str, Any] = Field(default_factory=dict)
    motivation_state: dict[str, Any] = Field(default_factory=dict)
    self_rewrite_history: list[dict[str, Any]] = Field(default_factory=list)


class BaselineRequest(BaseModel):
    profile: dict[str, Any]


class CheckpointRequest(BaseModel):
    brain_state: dict[str, Any]


def _get_auditor(request: Request) -> SanityAuditor:
    auditor = getattr(request.app.state, "sanity_auditor", None)
    if auditor is not None:
        return auditor
    auditor = SanityAuditor()
    request.app.state.sanity_auditor = auditor
    return auditor


@router.post("/sanity-auditor/baseline")
def set_baseline(payload: BaselineRequest, request: Request) -> dict[str, Any]:
    _get_auditor(request).set_baseline_profile(payload.profile)
    return {"status": "baseline_set", "profile": payload.profile}


@router.post("/sanity-auditor/checkpoints")
def create_checkpoint(payload: CheckpointRequest, request: Request) -> AuditCheckpoint:
    return _get_auditor(request).create_checkpoint(payload.brain_state)


@router.get("/sanity-auditor/checkpoints/{checkpoint_id}")
def get_checkpoint(checkpoint_id: str, request: Request) -> AuditCheckpoint:
    checkpoint = _get_auditor(request).get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"AuditCheckpoint {checkpoint_id} not found")
    return checkpoint


@router.post("/sanity-auditor/audits")
def run_audit(payload: SanityAuditRequest, request: Request) -> SanityAuditReport:
    return _get_auditor(request).audit(
        world_model=payload.world_model,
        strategy_graph=payload.strategy_graph,
        ban_layer=payload.ban_layer,
        motivation_state=payload.motivation_state,
        self_rewrite_history=payload.self_rewrite_history,
    )


@router.get("/sanity-auditor/audits")
def list_audits(request: Request) -> list[SanityAuditReport]:
    return _get_auditor(request).list_audits()


@router.get("/sanity-auditor/audits/{audit_id}")
def get_audit(audit_id: str, request: Request) -> SanityAuditReport:
    report = _get_auditor(request).get_audit(audit_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"SanityAuditReport {audit_id} not found")
    return report


@router.get("/sanity-auditor/audits/{audit_id}/self-modification-gate")
def get_self_modification_gate(audit_id: str, request: Request) -> dict[str, Any]:
    report = _get_auditor(request).get_audit(audit_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"SanityAuditReport {audit_id} not found")
    return {
        "audit_id": audit_id,
        "g18_self_shaping_allowed": not report.self_shaping_blocked,
        "g18_self_shaping_blocked": report.self_shaping_blocked,
        "self_shaping_blocked": report.self_shaping_blocked,
        "recommended_actions": [
            action.value if hasattr(action, "value") else str(action)
            for action in report.recommended_actions
        ],
        "disposition": report.disposition.value if hasattr(report.disposition, "value") else str(report.disposition),
        "summary": report.summary,
    }
