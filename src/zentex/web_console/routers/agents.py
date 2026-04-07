from __future__ import annotations
from typing import Any, Dict, List


from fastapi import APIRouter, HTTPException, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.agents.manager import AgentAsset
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest
from zentex.tasks.models import ZentexTask
from zentex.tasks.service import TaskManagementService
from zentex.web_console.contracts.agents import (
    AgentConsoleRecord,
    AgentInboxItem,
    AgentPolicyUpdateRequest,
    AgentReceiptItem,
    AgentDispatchTaskRequest,
    AgentAuditRecord,
)
from zentex.web_console.contracts.transcript import TranscriptEventPayload
from zentex.web_console.dependencies import get_agent_coordination_service
from zentex.web_console.dependencies import get_task_service, get_transcript_store
from zentex.web_console.transcript_serialization import serialize_transcript_entry


router = APIRouter()


@router.get("/agents", response_model=List[AgentConsoleRecord])
def list_agents(
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> List[AgentConsoleRecord]:
    tasks = task_service.list_tasks()
    records: List[AgentConsoleRecord] = []
    for asset in service.manager.list_assets():
        inbox_tasks = service.build_inbox(asset.agent_id, tasks)
        receipt_tasks = service.build_receipts(asset.agent_id, tasks)
        records.append(
            AgentConsoleRecord(
                agent_id=asset.agent_id,
                name=asset.name,
                agent_name=asset.agent_name,
                version=asset.version,
                function_description=asset.function_description,
                endpoint=asset.endpoint,
                role_tag=asset.role_tag,
                trust_level=asset.trust_level,
                status=asset.status,
                scope=list(asset.scope),
                capabilities=list(asset.capabilities),
                latency_ms=asset.latency_ms,
                success_rate=asset.success_rate,
                last_ping_at=asset.last_ping_at.isoformat() if asset.last_ping_at else None,
                registered_at=asset.registered_at.isoformat(),
                inbox=[
                    AgentInboxItem(
                        task_id=task.task_id,
                        title=task.title,
                        status=task.status.value,
                        idempotency_key=task.idempotency_key,
                        originator_id=task.originator_id,
                        remarks=task.remarks,
                    )
                    for task in inbox_tasks
                ],
                assigned_goal=service.build_assigned_goal(asset.agent_id, tasks),
                receipts=[
                    AgentReceiptItem(
                        task_id=task.task_id,
                        title=task.title,
                        status=task.status.value,
                        idempotency_key=task.idempotency_key,
                        completed_at=task.completed_at.isoformat() if task.completed_at else None,
                        remarks=task.remarks,
                    )
                    for task in receipt_tasks
                ],
            )
        )
    return records


@router.post("/agents/register", response_model=AgentAsset)
async def register_agent(
    payload: AgentRegistrationRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    request: Request,
) -> AgentAsset:
    return await service.register_agent(
        payload,
        operator_id=request.client.host if request.client else "unknown",
    )


@router.get("/agents/{agent_id}/handshake", response_model=AgentAsset)
async def trigger_handshake(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    await service.perform_handshake(agent_id)
    asset = service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Agent not found")
    return asset


@router.post("/agents/{agent_id}/safety-audit", response_model=AgentAsset)
async def trigger_safety_audit(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    try:
        await service.perform_safety_audit(agent_id)
        asset = service.manager.get_asset(agent_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Agent not found")
        return asset
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/dispatch")
async def dispatch_agent_task(
    agent_id: str,
    payload: AgentDispatchTaskRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> Dict[str, Any]:
    try:
        return await service.dispatch_task(agent_id, payload.task_payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/agents/{agent_id}")
async def unregister_agent(
    agent_id: str,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    request: Request,
) -> Dict[str, bool]:
    success = await service.unregister_agent(
        agent_id,
        operator_id=request.client.host if request.client else "unknown",
    )
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"success": True}


@router.get("/agents-health/status")
async def monitor_agents_health(
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> List[AgentAsset]:
    return await service.monitor_health()


@router.patch("/agents/{agent_id}/policy", response_model=AgentAsset)
async def update_agent_policy(
    agent_id: str,
    payload: AgentPolicyUpdateRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
) -> AgentAsset:
    try:
        return await service.update_policy(
            agent_id,
            trust_level=payload.trust_level,
            scope=payload.scope,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/tasks", response_model=List[ZentexTask])
def list_agent_tasks(
    agent_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> List[ZentexTask]:
    return [task for task in service.list_tasks() if task.target_id == agent_id]


@router.get("/agents/{agent_id}/audit", response_model=List[AgentAuditRecord])
def list_agent_audit_events(
    agent_id: str,
    request: Request,
) -> List[AgentAuditRecord]:
    store = get_transcript_store(request)
    events: List[AgentAuditRecord] = []
    for entry in reversed(store.get_entries_snapshot()):
        if entry.session_id != "agent-management-audit":
            continue
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        if str(payload.get("agent_id") or "") != agent_id:
            continue
            
        events.append(AgentAuditRecord(
            agent_id=agent_id,
            event_type=str(payload.get("event_type") or "UNKNOWN"),
            timestamp=entry.timestamp.isoformat(),
            summary=str(payload.get("summary") or ""),
            details=payload.get("details") if isinstance(payload.get("details"), dict) else {}
        ))
        if len(events) >= 200:
            break
    events.reverse()
    return events
