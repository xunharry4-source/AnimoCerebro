from __future__ import annotations

"""Web API for the unified plugin bus."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from zentex.plugins.contracts import PluginLifecycleStatus
from zentex.plugins.unified_plugin_bus import PluginFamily, UnifiedPluginBus, UnifiedPluginSpec


router = APIRouter(prefix="/plugin-bus/g43", tags=["plugin-bus-g43"])


class PluginPromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: PluginLifecycleStatus
    reason: str


class PluginSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: dict[str, Any]


class PluginPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_ids: list[str]


class PluginInvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]


class PluginGovernanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str


def _bus(request: Request) -> UnifiedPluginBus:
    bus = getattr(request.app.state, "unified_plugin_bus", None)
    if bus is None:
        bus = UnifiedPluginBus()
        request.app.state.unified_plugin_bus = bus
    return bus


@router.post("/plugins")
def register_plugin(payload: UnifiedPluginSpec, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).register_plugin(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "plugin_registration_rejected", "message": str(exc)}) from exc


@router.get("/plugins")
def list_plugins(request: Request, family: PluginFamily | None = None, status: PluginLifecycleStatus | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _bus(request).list_plugins(family=family, status=status)]


@router.get("/plugins/{plugin_id}")
def get_plugin(plugin_id: str, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).get_plugin(plugin_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "plugin_not_found"}) from exc


@router.post("/plugins/{plugin_id}/sandbox-verify")
def verify_plugin(plugin_id: str, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).verify_sandbox(plugin_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "plugin_not_found"}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail={"error": "plugin_sandbox_verification_failed", "message": str(exc)}) from exc


@router.post("/plugins/{plugin_id}/promote")
def promote_plugin(plugin_id: str, payload: PluginPromotionRequest, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).promote_plugin(plugin_id, payload.target_status, reason=payload.reason).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "plugin_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "plugin_promotion_rejected", "message": str(exc)}) from exc


@router.post("/selection")
def select_plugins(payload: PluginSelectionRequest, request: Request) -> dict[str, Any]:
    return _bus(request).select_plugins(payload.context).model_dump(mode="json")


@router.post("/plans")
def build_plan(payload: PluginPlanRequest, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).build_invocation_plan(payload.plugin_ids).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail={"error": "plugin_plan_rejected", "message": str(exc)}) from exc


@router.post("/plugins/{plugin_id}/invoke")
def invoke_plugin(plugin_id: str, payload: PluginInvocationRequest, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).invoke_plugin(plugin_id, payload.payload).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "plugin_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "plugin_invocation_rejected", "message": str(exc)}) from exc


@router.post("/plugins/{plugin_id}/degrade")
def degrade_plugin(plugin_id: str, payload: PluginGovernanceRequest, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).degrade_plugin(plugin_id, reason=payload.reason).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "plugin_not_found"}) from exc


@router.post("/plugins/{plugin_id}/revoke")
def revoke_plugin(plugin_id: str, payload: PluginGovernanceRequest, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).revoke_plugin(plugin_id, reason=payload.reason).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "plugin_not_found"}) from exc


@router.post("/plugins/{plugin_id}/rollback")
def rollback_plugin(plugin_id: str, payload: PluginGovernanceRequest, request: Request) -> dict[str, Any]:
    try:
        return _bus(request).rollback_plugin(plugin_id, reason=payload.reason).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "plugin_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "plugin_rollback_rejected", "message": str(exc)}) from exc


@router.get("/family-coverage")
def family_coverage(request: Request) -> dict[str, Any]:
    return _bus(request).family_coverage()


@router.get("/closure/diagnostics")
def diagnose_plugin_closure(request: Request, run_health_probes: bool = True) -> dict[str, Any]:
    return _bus(request).diagnose_acceptance_closure(run_health_probes=run_health_probes).model_dump(mode="json")


@router.post("/closure/fault-injection")
def run_plugin_fault_injection(request: Request) -> dict[str, Any]:
    return _bus(request).run_fault_injection_matrix().model_dump(mode="json")


@router.get("/closure/completion")
def plugin_completion_report(request: Request, run_health_probes: bool = True) -> dict[str, Any]:
    return _bus(request).completion_report(run_health_probes=run_health_probes).model_dump(mode="json")


@router.get("/audit")
def list_audit(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _bus(request).list_audit_events()]
