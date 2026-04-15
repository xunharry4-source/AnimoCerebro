"""
Agent Route Handlers — Business logic for agent management.
Extracted from agents.py to follow the Facade-First / Thin-Route pattern.
"""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import HTTPException, Request

from zentex.agents.service import AgentCoordinationService, AgentAsset
from zentex.tasks.service import TaskManagementService
from zentex.web_console.contracts.agents import (
    AgentConsoleRecord,
    AgentInboxItem,
    AgentReceiptItem,
    AgentAuditRecord,
)
from zentex.web_console.services.agents import (
    calculate_agent_credit_score,
    get_agent_statistics,
)


def handle_list_agents(
    service: AgentCoordinationService,
    task_service: TaskManagementService,
) -> List[AgentConsoleRecord]:
    """Handle the listing of agents with their inbox and receipts."""
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


def handle_get_agent_audit_events(
    agent_id: str,
    transcript_store: Any,
) -> List[AgentAuditRecord]:
    """Handle auditing events for a specific agent."""
    events: List[AgentAuditRecord] = []
    # Safeguard against missing transcript store
    if transcript_store is None:
        return []
        
    for entry in reversed(transcript_store.get_entries_snapshot()):
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


def handle_get_agent_detail(
    agent_id: str,
    agent_service: AgentCoordinationService,
    task_service: TaskManagementService,
) -> Dict[str, Any]:
    """Handle detailed agent information retrieval."""
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    tasks = task_service.list_tasks()
    inbox_tasks = agent_service.build_inbox(agent_id, tasks)
    receipt_tasks = agent_service.build_receipts(agent_id, tasks)
    
    credit_score = calculate_agent_credit_score(agent_id, agent_service, task_service)
    statistics = get_agent_statistics(agent_id, task_service)
    
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
                "task_id": t.task_id,
                "title": t.title,
                "status": t.status.value,
                "idempotency_key": t.idempotency_key,
                "originator_id": t.originator_id,
                "remarks": t.remarks,
            }
            for t in inbox_tasks
        ],
        "receipts": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "status": t.status.value,
                "idempotency_key": t.idempotency_key,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "remarks": t.remarks,
            }
            for t in receipt_tasks
        ],
        "credit_score": credit_score,
        "statistics": statistics,
    }


def handle_cancel_agent_task(
    agent_id: str,
    task_id: str,
    agent_service: AgentCoordinationService,
    task_service: TaskManagementService,
) -> Dict[str, Any]:
    """Handle task cancellation for an agent."""
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    task = None
    for t in task_service.list_tasks():
        if t.task_id == task_id and t.target_id == agent_id:
            task = t
            break
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found for agent {agent_id}")
    
    if task.status.value in ["done", "failed", "cancelled"]:
        raise HTTPException(status_code=409, detail=f"Cannot cancel task with status: {task.status.value}")
    
    try:
        task_service.update_task_status(task_id, "cancelled")
        return {"success": True, "message": f"Task {task_id} has been cancelled", "task_id": task_id, "new_status": "cancelled"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


def handle_retry_agent_task(
    agent_id: str,
    task_id: str,
    agent_service: AgentCoordinationService,
    task_service: TaskManagementService,
) -> Dict[str, Any]:
    """Handle task retry for an agent."""
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    task = None
    for t in task_service.list_tasks():
        if t.task_id == task_id and t.target_id == agent_id:
            task = t
            break
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found for agent {agent_id}")
    
    if task.status.value != "failed":
        raise HTTPException(status_code=409, detail=f"Can only retry failed tasks. Current status: {task.status.value}")
    
    try:
        task_service.update_task_status(task_id, "todo")
        return {"success": True, "message": f"Task {task_id} has been reset to todo for retry", "task_id": task_id, "new_status": "todo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry task: {str(e)}")
