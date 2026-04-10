from __future__ import annotations
from typing import Any, Dict, List, Optional


from fastapi import APIRouter, HTTPException, Query, Request
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
from zentex.web_console.services.agents import (
    calculate_agent_credit_score,
    get_agent_statistics,
    get_tasks_by_status,
)


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


@router.get("/agents/{agent_id}/detail")
def get_agent_detail(
    agent_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """
    Get detailed information about an agent including credit score and statistics.
    """
    # Get basic agent info
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Get tasks for inbox and receipts
    tasks = task_service.list_tasks()
    inbox_tasks = agent_service.build_inbox(agent_id, tasks)
    receipt_tasks = agent_service.build_receipts(agent_id, tasks)
    
    # Calculate credit score
    try:
        credit_score = calculate_agent_credit_score(agent_id, agent_service, task_service)
    except Exception as e:
        credit_score = {
            "total_score": 0,
            "dimensions": [],
            "history": [],
            "error": str(e),
        }
    
    # Get statistics
    try:
        statistics = get_agent_statistics(agent_id, task_service)
    except Exception as e:
        statistics = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "in_progress_tasks": 0,
            "pending_tasks": 0,
            "avg_completion_time": 0,
            "uptime_percentage": 0,
            "error": str(e),
        }
    
    return {
        "agent_id": asset.agent_id,
        "name": asset.name,
        "agent_name": asset.agent_name,
        "version": asset.version,
        "function_description": asset.function_description,
        "endpoint": asset.endpoint,
        "role_tag": asset.role_tag,
        "trust_level": asset.trust_level,
        "status": asset.status,
        "scope": list(asset.scope),
        "capabilities": list(asset.capabilities),
        "latency_ms": asset.latency_ms,
        "success_rate": asset.success_rate,
        "last_ping_at": asset.last_ping_at.isoformat() if asset.last_ping_at else None,
        "registered_at": asset.registered_at.isoformat(),
        "assigned_goal": agent_service.build_assigned_goal(agent_id, tasks),
        "inbox": [
            {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "idempotency_key": task.idempotency_key,
                "originator_id": task.originator_id,
                "remarks": task.remarks,
            }
            for task in inbox_tasks
        ],
        "receipts": [
            {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "idempotency_key": task.idempotency_key,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "remarks": task.remarks,
            }
            for task in receipt_tasks
        ],
        "credit_score": credit_score,
        "statistics": statistics,
    }


@router.get("/agents/{agent_id}/tasks/by-status")
def get_agent_tasks_by_status(
    agent_id: str,
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
    status: str = Query(..., description="Comma-separated status values"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("started_at", description="Sort field"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    search: str = Query("", description="Search in task title or ID"),
    task_type: str = Query("", description="Filter by task type"),
    originator: str = Query("", description="Filter by originator ID"),
    date_from: str = Query("", description="Filter from date (ISO format)"),
    date_to: str = Query("", description="Filter to date (ISO format)"),
) -> Dict[str, Any]:
    """
    Get tasks for an agent filtered by status with pagination and advanced filtering support.
    """
    # Verify agent exists
    agent_service: AgentCoordinationService = get_agent_coordination_service()
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    return get_tasks_by_status(
        agent_id=agent_id,
        status_filter=status,
        task_service=task_service,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
        search=search,
        task_type=task_type,
        originator=originator,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/agents/{agent_id}/tasks/{task_id}/cancel")
def cancel_agent_task(
    agent_id: str,
    task_id: str,
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """
    Cancel a task for an agent.
    """
    # Verify agent exists
    agent_service: AgentCoordinationService = get_agent_coordination_service()
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Find the task
    task = None
    for t in task_service.list_tasks():
        if t.task_id == task_id and t.target_id == agent_id:
            task = t
            break
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found for agent {agent_id}")
    
    # Check if task can be cancelled
    if task.status.value in ["done", "failed", "cancelled"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel task with status: {task.status.value}"
        )
    
    # Cancel the task (update status)
    try:
        task_service.update_task_status(task_id, "cancelled")
        return {
            "success": True,
            "message": f"Task {task_id} has been cancelled",
            "task_id": task_id,
            "new_status": "cancelled"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


@router.post("/agents/{agent_id}/tasks/{task_id}/retry")
def retry_agent_task(
    agent_id: str,
    task_id: str,
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """
    Retry a failed task for an agent.
    """
    # Verify agent exists
    agent_service: AgentCoordinationService = get_agent_coordination_service()
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Find the task
    task = None
    for t in task_service.list_tasks():
        if t.task_id == task_id and t.target_id == agent_id:
            task = t
            break
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found for agent {agent_id}")
    
    # Check if task can be retried (only failed tasks)
    if task.status.value != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Can only retry failed tasks. Current status: {task.status.value}"
        )
    
    # Retry the task (reset to todo status)
    try:
        task_service.update_task_status(task_id, "todo")
        return {
            "success": True,
            "message": f"Task {task_id} has been reset to todo for retry",
            "task_id": task_id,
            "new_status": "todo"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry task: {str(e)}")
