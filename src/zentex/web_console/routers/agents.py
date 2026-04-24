from __future__ import annotations
"""
Agents Router — HTTP route handlers for agent management and task coordination.

RESPONSIBILITY:
  Exposes REST endpoints for registering, monitoring, and coordinating
  AgentAsset objects.  Does NOT implement agent logic; all coordination
  delegates to AgentCoordinationService and TaskManagementService obtained
  via FastAPI Depends().

CAPABILITIES:
  - GET    /agents                          — list agents with task inbox/receipts
  - POST   /agents/register                 — register a new agent
  - GET    /agents/{id}/handshake           — trigger handshake
  - POST   /agents/{id}/safety-audit        — trigger safety audit
  - POST   /agents/{id}/dispatch            — dispatch a task to an agent
  - DELETE /agents/{id}                     — unregister an agent
  - GET    /agents-health/status            — health check across all agents
  - PATCH  /agents/{id}/policy             — update trust level / scope
  - GET    /agents/{id}/tasks              — list tasks for an agent
  - GET    /agents/{id}/audit              — audit events from transcript store
  - GET    /agents/{id}/detail             — credit score + statistics
  - GET    /agents/{id}/tasks/by-status    — paginated status-filtered task view
  - POST   /agents/{id}/tasks/{tid}/cancel — cancel a task
  - POST   /agents/{id}/tasks/{tid}/retry  — retry a failed task

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  - get_agent_coordination_service() and get_task_service() raise HTTPException(503)
    when the underlying service is None.  Route handlers always receive valid
    service objects, never None.

DOES NOT:
  - Own AgentCoordinationService, TaskManagementService, or TranscriptStore.
  - Implement agent handshake, safety-audit, or dispatch logic directly.
  - Silently return empty results when a required service is absent.
"""

import logging
from typing import Any, Dict, List, Optional


from fastapi import APIRouter, HTTPException, Query, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.agents.service import AgentAsset, AgentCoordinationService, AgentRegistrationRequest
from zentex.agents.bridge import AgentBridgeError

logger = logging.getLogger(__name__)
from zentex.tasks.service import TaskManagementService, ZentexTask
from zentex.web_console.contracts.agents import (
    AgentConsoleRecord,
    AgentPolicyUpdateRequest,
    AgentDispatchTaskRequest,
    AgentAuditRecord,
)
from zentex.web_console.dependencies import (
    get_agent_coordination_service,
    get_task_service,
    get_kernel_service_facade,
)
from zentex.web_console.contracts.kernel_service import KernelServiceFacade
from zentex.web_console.services.agents import get_tasks_by_status as handle_get_tasks_by_status
from .agents_handlers import (
    handle_list_agents,
    handle_get_agent_audit_events,
    handle_get_agent_detail,
    handle_cancel_agent_task,
    handle_retry_agent_task,
)


router = APIRouter()


@router.get("/agents", response_model=List[AgentConsoleRecord])
def list_agents(
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> List[AgentConsoleRecord]:
    """获取所有智能体及其收件箱/回执列表"""
    return handle_list_agents(service, task_service)


@router.post("/agents/register", response_model=AgentAsset)
async def register_agent(
    payload: AgentRegistrationRequest,
    service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    request: Request,
) -> AgentAsset:
    try:
        return await service.register_agent(
            payload,
            operator_id=request.client.host if request.client else "unknown",
        )
    except AgentBridgeError as exc:
        # Unreachable endpoint or protocol error — reject registration with 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Agent registration failed unexpectedly")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    return service.list_tasks(target_id=agent_id)


@router.get("/agents/{agent_id}/audit", response_model=List[AgentAuditRecord])
def list_agent_audit_events(
    agent_id: str,
    request: Request,
) -> List[AgentAuditRecord]:
    """获取所有智能体的审计日志"""
    audit_service = getattr(request.app.state, "audit_service", None)
    return handle_get_agent_audit_events(agent_id, audit_service)


@router.get("/agents/{agent_id}/detail")
def get_agent_detail(
    agent_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """获取智能体详细详情（含信用分、统计信息、收发件箱）"""
    return handle_get_agent_detail(agent_id, agent_service, task_service)


@router.get("/agents/{agent_id}/tasks/by-status")
def get_agent_tasks_view(
    agent_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
    status: str = Query(..., description="状态过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("started_at"),
    order: str = Query("desc"),
    search: str = Query(""),
    task_type: str = Query(""),
    originator: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
) -> Dict[str, Any]:
    """带分页和过滤的智能体任务视图"""
    return handle_get_tasks_by_status(
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
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    return handle_cancel_agent_task(agent_id, task_id, agent_service, task_service)


@router.post("/agents/{agent_id}/tasks/{task_id}/retry")
def retry_agent_task(
    agent_id: str,
    task_id: str,
    agent_service: Annotated[AgentCoordinationService, Depends(get_agent_coordination_service)],
    task_service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    return handle_retry_agent_task(agent_id, task_id, agent_service, task_service)
