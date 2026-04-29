"""Web API for G35 role switching and multi-agent governance."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.agents.governance import (
    AgentTaskRequest,
    CollaborationOutcome,
    GovernedAgentRegistration,
    RoleAgentGovernanceManager,
    RoleOverrideRequest,
    TaskRoleInferenceRequest,
)

router = APIRouter(prefix="/role-agent-governance", tags=["role-agent-governance"])


def _manager(request: Request) -> RoleAgentGovernanceManager:
    manager = getattr(request.app.state, "role_agent_governance_manager", None)
    if manager is None:
        manager = RoleAgentGovernanceManager(
            model_provider_runtime=getattr(request.app.state, "model_provider_runtime", None),
            default_llm_provider_id=getattr(request.app.state, "default_governance_llm_provider_id", None),
        )
        request.app.state.role_agent_governance_manager = manager
    return manager


@router.get("/roles")
def get_roles(request: Request) -> dict[str, Any]:
    return _manager(request).get_role_state().model_dump(mode="json")


@router.post("/roles/active-override")
def override_active_role(payload: RoleOverrideRequest, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).override_active_role(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "role_override_failed", "message": str(exc)}) from exc


@router.post("/roles/task-role")
def infer_task_role(payload: TaskRoleInferenceRequest, request: Request) -> dict[str, Any]:
    return _manager(request).infer_task_role(payload).model_dump(mode="json")


@router.post("/agents/register")
def register_agent(payload: GovernedAgentRegistration, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).register_agent(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "agent_registration_failed", "message": str(exc)}) from exc


@router.get("/agents")
def list_agents(request: Request) -> list[dict[str, Any]]:
    return [agent.model_dump(mode="json") for agent in _manager(request).list_agents()]


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).get_agent(agent_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "agent_not_found", "message": str(exc)}) from exc


@router.post("/agents/{agent_id}/monitor")
def monitor_agent(agent_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).monitor_agent(agent_id).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 400
        raise HTTPException(status_code=status, detail={"error": "agent_monitor_failed", "message": str(exc)}) from exc


@router.post("/agents/schedule")
def schedule_agent(payload: AgentTaskRequest, request: Request) -> dict[str, Any]:
    return _manager(request).schedule_task(payload).model_dump(mode="json")


@router.post("/agents/{agent_id}/test-task")
def submit_test_task(agent_id: str, payload: AgentTaskRequest, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).submit_test_task(agent_id, payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail={"error": "agent_test_task_failed", "message": str(exc)}) from exc


@router.get("/agents/{agent_id}/receipts/{receipt_id}")
def verify_receipt(agent_id: str, receipt_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).verify_receipt(agent_id, receipt_id).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail={"error": "receipt_verification_failed", "message": str(exc)}) from exc


@router.get("/conflicts")
def conflicts(request: Request) -> list[dict[str, Any]]:
    return [conflict.model_dump(mode="json") for conflict in _manager(request).detect_conflicts()]


@router.post("/outcomes")
def record_outcome(payload: CollaborationOutcome, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).record_outcome(payload).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "agent_not_found", "message": str(exc)}) from exc


@router.get("/outcomes")
def list_outcomes(request: Request, agent_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _manager(request).list_outcomes(agent_id=agent_id)]


@router.get("/external-interface")
def external_interface(request: Request) -> dict[str, Any]:
    return _manager(request).external_interface()


@router.get("/closure/diagnostics")
def diagnose_agent_governance_closure(request: Request, heartbeat_freshness_seconds: int = 300) -> dict[str, Any]:
    return _manager(request).diagnose_agent_governance_closure(heartbeat_freshness_seconds=heartbeat_freshness_seconds)


@router.post("/closure/enforce")
def enforce_agent_governance_closure(request: Request, heartbeat_freshness_seconds: int = 300) -> dict[str, Any]:
    return _manager(request).enforce_agent_governance_closure(heartbeat_freshness_seconds=heartbeat_freshness_seconds)


@router.post("/closure/fault-injection")
def run_agent_fault_injection_matrix(request: Request, heartbeat_freshness_seconds: int = 300) -> dict[str, Any]:
    return _manager(request).run_agent_fault_injection_matrix(heartbeat_freshness_seconds=heartbeat_freshness_seconds)


@router.get("/audit")
def audit(request: Request) -> list[dict[str, Any]]:
    return [event.model_dump(mode="json") for event in _manager(request).list_audit_events()]
