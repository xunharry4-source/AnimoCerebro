from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from typing_extensions import Annotated
from fastapi import Depends, Query

from zentex.tasks.service import TaskManagementService, ZentexTask, TaskStatus, TaskStateError, TaskType
from zentex.web_console.dependencies import get_task_service


router = APIRouter()


@router.get("/tasks", response_model=List[ZentexTask])
async def list_tasks(
    service: Annotated[TaskManagementService, Depends(get_task_service)],
    status_filter: Optional[str] = Query(None, description="Filter by status"),
) -> List[ZentexTask]:
    """List all tasks with optional status filter."""
    if status_filter:
        try:
            status_enum = TaskStatus(status_filter)
            return service.list_tasks(status=status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
    return service.list_tasks()


@router.get("/tasks/by-status")
async def get_tasks_by_status(
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, List[ZentexTask]]:
    """Get tasks grouped by status categories for tabbed view."""
    return {
        "in_progress": service.list_tasks(status=TaskStatus.IN_PROGRESS),
        "pending": service.list_tasks(status=TaskStatus.TODO) + 
                   service.list_tasks(status=TaskStatus.BLOCKED),
        "waiting_confirmation": service.list_tasks(status=TaskStatus.WAITING_CONFIRMATION),
        "completed": service.list_tasks(status=TaskStatus.DONE),
        "cancelled": service.list_tasks(status=TaskStatus.FAILED) + 
                     service.list_tasks(status=TaskStatus.SUSPENDED) + 
                     service.list_tasks(status=TaskStatus.ARCHIVED)
    }


@router.get("/tasks/{task_id}/detail")
async def get_task_detail(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """Get complete task details including subtasks and history."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # Get subtasks
    subtasks = []
    for subtask_id in task.subtask_ids:
        subtask = service.get_task(subtask_id)
        if subtask:
            subtasks.append(subtask.model_dump(mode="json"))
    
    # Get dependency info
    dependencies = []
    for dep_id in task.depends_on:
        dep_task = service.get_task(dep_id)
        if dep_task:
            dependencies.append({
                "task_id": dep_id,
                "title": dep_task.title,
                "status": dep_task.status.value
            })
    
    # Get dependent tasks (tasks that depend on this task)
    dependent_tasks = service.get_dependent_tasks(task_id)
    dependents = [{
        "task_id": t.task_id,
        "title": t.title,
        "status": t.status.value
    } for t in dependent_tasks]
    
    # Get intervention records for this task
    interventions = [
        receipt for receipt in service._intervention_receipts.values()
        if receipt.get("task_id") == task_id
    ]
    
    return {
        "task": task.model_dump(mode="json"),
        "subtasks": subtasks,
        "subtask_count": len(subtasks),
        "dependencies": dependencies,
        "dependents": dependents,
        "interventions": interventions,
        "statistics": {
            "total_subtasks": len(subtasks),
            "completed_subtasks": sum(1 for st in subtasks if st["status"] == "done"),
            "in_progress_subtasks": sum(1 for st in subtasks if st["status"] == "in_progress"),
            "pending_subtasks": sum(1 for st in subtasks if st["status"] in ["todo", "blocked"]),
            "failed_subtasks": sum(1 for st in subtasks if st["status"] == "failed")
        }
    }


@router.get("/tasks/{task_id}/subtasks")
async def get_subtasks(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
    status_filter: Optional[str] = Query(None, description="Filter subtasks by status"),
) -> Dict[str, Any]:
    """Get all subtasks for a given task."""
    parent_task = service.get_task(task_id)
    if not parent_task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    subtasks = []
    for subtask_id in parent_task.subtask_ids:
        subtask = service.get_task(subtask_id)
        if subtask:
            if status_filter:
                try:
                    status_enum = TaskStatus(status_filter)
                    if subtask.status == status_enum:
                        subtasks.append(subtask)
                except ValueError:
                    subtasks.append(subtask)
            else:
                subtasks.append(subtask)
    
    # Calculate statistics
    stats = {
        "total": len(parent_task.subtask_ids),
        "returned": len(subtasks),
        "by_status": {}
    }
    
    for st in subtasks:
        status = st.status.value
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
    
    return {
        "parent_task_id": task_id,
        "subtasks": [st.model_dump(mode="json") for st in subtasks],
        "statistics": stats
    }


@router.post("/tasks/{task_id}/decompose")
async def decompose_task(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
    payload: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Manually trigger task decomposition."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    force_decompose = payload.get("force_decompose", False) if payload else False
    
    # Only MISSION tasks or forced decomposition allowed
    if task.task_type != TaskType.MISSION and not force_decompose:
        raise HTTPException(
            status_code=400,
            detail="Only mission tasks can be decomposed. Use force_decompose=true to override."
        )
    
    # Trigger decomposition
    await service.decompose_and_dispatch_mission(task)
    
    return {
        "message": "Task decomposition initiated",
        "task_id": task_id,
        "subtask_count": len(task.subtask_ids)
    }


@router.get("/tasks/{task_id}/execution-history")
async def get_execution_history(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """Get complete execution history and audit trail for a task."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # Get subtasks
    subtasks = []
    for subtask_id in task.subtask_ids:
        subtask = service.get_task(subtask_id)
        if subtask:
            subtasks.append(subtask.model_dump(mode="json"))
    
    # Get intervention records
    interventions = [
        receipt for receipt in service._intervention_receipts.values()
        if receipt.get("task_id") == task_id
    ]
    
    return {
        "task": task.model_dump(mode="json"),
        "subtasks": subtasks,
        "interventions": interventions,
        "audit_trail": {
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "last_updated_at": task.last_updated_at.isoformat(),
            "status_changes": len(interventions),
            "total_interventions": len(interventions)
        }
    }


@router.websocket("/tasks/stream")
async def stream_task_updates(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time task updates.
    
    Sends task list updates whenever tasks change.
    Clients should reconnect on disconnect to resume monitoring.
    """
    await websocket.accept()
    service: TaskManagementService = get_task_service(type('obj', (object,), {'app': websocket.app})())
    
    if service is None:
        await websocket.close(code=1011, reason="Task service is not available")
        return
    
    last_task_count = len(service.list_tasks())
    last_revision = getattr(service, '_revision', 0)
    
    try:
        while True:
            # Check for disconnect
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1.0)
                if message.get("type") == "websocket.disconnect":
                    return
            except asyncio.TimeoutError:
                pass  # No message received, continue checking for updates
            
            # Check if tasks have changed
            current_tasks = service.list_tasks()
            current_count = len(current_tasks)
            current_revision = getattr(service, '_revision', 0)
            
            if current_count != last_task_count or current_revision != last_revision:
                # Tasks have changed, send update
                await websocket.send_json({
                    "type": "task_update",
                    "tasks": [task.model_dump(mode="json") for task in current_tasks],
                    "count": current_count,
                    "timestamp": asyncio.get_event_loop().time()
                })
                last_task_count = current_count
                last_revision = current_revision
                
    except WebSocketDisconnect:
        return
    except RuntimeError:
        return


@router.get("/tasks/tree/{task_id}")
async def get_task_tree(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> Dict[str, Any]:
    """Get hierarchical task tree (Goal Tree)."""
    try:
        return service.get_dependency_tree(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/negotiations")
async def list_negotiations(
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> List[Any]:
    """List auto-generated negotiations for capability gaps."""
    # Trigger a scan first
    service.trigger_negotiation_scans()
    # List active negotiations
    return list(service.negotiation_generator._active_negotiations.values())


@router.post("/tasks/{task_id}/intervene")
async def intervene_task(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(get_task_service)],
    request: Request,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        action = str(payload.get("action") or "").strip()
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        remarks = payload.get("remarks")
        operator_id = str(
            payload.get("operator_id")
            or (request.client.host if request.client else "unknown")
        )
        if remarks is not None and not isinstance(remarks, str):
            remarks = str(remarks)
        return service.intervene(
            task_id,
            action=action,
            idempotency_key=idempotency_key,
            remarks=remarks,
            operator_id=operator_id,
        )
    except TaskStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/bulk-operation")
async def bulk_operation(
    service: Annotated[TaskManagementService, Depends(get_task_service)],
    request: Request,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Perform bulk operations on multiple tasks."""
    task_ids = payload.get("task_ids", [])
    action = payload.get("action", "")
    operator_id = str(
        payload.get("operator_id")
        or (request.client.host if request.client else "unknown")
    )
    remarks = payload.get("remarks", "")
    
    if not task_ids:
        raise HTTPException(status_code=400, detail="task_ids is required")
    
    results = {"success": [], "failed": []}
    
    for task_id in task_ids:
        try:
            if action == "pause":
                service.update_task_status(task_id, TaskStatus.BLOCKED, remarks=remarks)
            elif action == "resume":
                service.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks=remarks)
            elif action == "approve":
                service.update_task_status(task_id, TaskStatus.DONE, remarks=remarks)
            elif action == "reject":
                service.update_task_status(task_id, TaskStatus.FAILED, remarks=remarks)
            elif action == "archive":
                service.update_task_status(task_id, TaskStatus.ARCHIVED, remarks=remarks)
            else:
                results["failed"].append({
                    "task_id": task_id,
                    "error": f"Unknown action: {action}"
                })
                continue
            
            results["success"].append({
                "task_id": task_id,
                "action": action
            })
        except Exception as e:
            results["failed"].append({
                "task_id": task_id,
                "error": str(e)
            })
    
    return {
        "action": action,
        "total": len(task_ids),
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
        "results": results
    }
