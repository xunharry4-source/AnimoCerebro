from __future__ import annotations
"""
Tasks Router — HTTP route handlers for task management operations.

RESPONSIBILITY:
  Exposes REST endpoints and a WebSocket stream for CRUD, status-filtering,
  intervention, bulk-operations, and decomposition of ZentexTask objects.
  Does NOT implement business logic; all mutations delegate to
  TaskManagementService obtained via _require_task_service().

CAPABILITIES:
  - GET  /tasks                    — list tasks with optional status filter
  - GET  /tasks/by-status          — tasks grouped by status category
  - GET  /tasks/{id}/detail        — full task record with subtasks & deps
  - GET  /tasks/{id}/subtasks      — paginated subtask list
  - GET  /tasks/{id}/execution-history — audit trail
  - GET  /tasks/tree/{id}          — hierarchical Goal Tree
  - GET  /tasks/negotiations       — auto-generated negotiations
  - POST /tasks/{id}/decompose     — trigger mission decomposition
  - POST /tasks/{id}/intervene     — manual status override
  - POST /tasks/bulk-operation     — batch status transitions
  - WS   /tasks/stream             — real-time task-update stream

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  - _require_task_service() chains Depends(get_task_service) and raises 503
    when the service is None.  Routes never receive None.
  - The WebSocket handler wraps the dependency call in try/except so a missing
    service closes the WS cleanly (code 1011) rather than crashing.

DOES NOT:
  - Own TaskManagementService or its lifecycle.
  - Silently return empty results when the service is absent.
  - Implement decomposition, negotiation, or consolidation logic directly.
"""


import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from typing_extensions import Annotated
from fastapi import Depends, Query, Body

from zentex.tasks.service import TaskManagementService, ZentexTask, TaskStatus, TaskStateError, TaskType
from zentex.web_console.dependencies import get_task_service
from .tasks_handlers import (
    handle_get_task_detail,
    handle_get_subtasks,
    handle_get_execution_history,
    handle_bulk_operation,
)


router = APIRouter()
logger = logging.getLogger(__name__)


def _require_task_service(service: Any = Depends(get_task_service)) -> TaskManagementService:
    """Fail-closed Depends wrapper: raise 503 when task service is not available.

    A stub service (``_is_stub=True``) is treated the same as None — the tasks
    module failed to initialise, so all routes must return 503 rather than
    silently returning empty/None results that break response validation.
    """
    if service is None or getattr(service, "_is_stub", False):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "task_service_unavailable",
                "message": "TaskManagementService 未初始化，任务功能不可用。",
            },
        )
    return service


def _parse_metadata_filters(raw_filters: Optional[List[str]]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for raw_filter in raw_filters or []:
        for item in raw_filter.split(","):
            if not item:
                continue
            if "=" not in item:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid metadata filter '{item}'. Expected key=value.",
                )
            key, value = item.split("=", 1)
            key = key.strip()
            if not key:
                raise HTTPException(status_code=400, detail="Metadata filter key must not be empty")
            parsed[key] = value
    return parsed


@router.get("/tasks", response_model=List[ZentexTask])
async def list_tasks(
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    source_module: Optional[str] = Query(None, description="Filter by workflow source module"),
    metadata_filters: Optional[List[str]] = Query(
        None,
        description="Metadata filters as key=value pairs; repeat the parameter or separate with commas.",
    ),
    limit: int = Query(100, ge=1, le=500, description="Maximum tasks to return"),
    offset: int = Query(0, ge=0, description="Database offset for pagination"),
) -> List[ZentexTask]:
    """List tasks with database-backed filters and pagination."""
    parsed_metadata_filters = _parse_metadata_filters(metadata_filters)
    if status_filter:
        try:
            status_enum = TaskStatus(status_filter)
            return service.list_tasks(
                status=status_enum,
                source_module=source_module,
                metadata_filters=parsed_metadata_filters,
                limit=limit,
                offset=offset,
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
    return service.list_tasks(
        source_module=source_module,
        metadata_filters=parsed_metadata_filters,
        limit=limit,
        offset=offset,
    )


@router.get("/tasks/by-status")
async def get_tasks_grouped_by_status(
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    source_module: Optional[str] = Query(None, description="Filter grouped tasks by workflow source module"),
    limit_per_group: int = Query(100, ge=1, le=500, description="Maximum tasks per group"),
    offset: int = Query(0, ge=0, description="Database offset applied to each status query"),
) -> Dict[str, List[ZentexTask]]:
    """Get paginated tasks grouped by status categories for tabbed view.

    Grouping rules are owned by TaskManagementService.list_tasks_grouped().
    """
    return service.list_tasks_grouped(
        source_module=source_module,
        limit_per_group=limit_per_group,
        offset=offset,
    )


@router.get("/tasks/diagnostics/closure")
async def diagnose_task_management_closure(
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    stale_after_seconds: int = Query(300, ge=0),
) -> Dict[str, Any]:
    return service.diagnose_task_management_closure(stale_after_seconds=stale_after_seconds)


@router.post("/tasks/diagnostics/fault-injection")
async def run_task_fault_injection_matrix(
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    stale_after_seconds: int = Query(300, ge=0),
) -> Dict[str, Any]:
    return service.run_task_fault_injection_matrix(stale_after_seconds=stale_after_seconds)


@router.get("/tasks/{task_id}/detail")
async def get_task_detail(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
) -> Dict[str, Any]:
    return handle_get_task_detail(task_id, service)


@router.get("/tasks/{task_id}/subtasks")
async def get_subtasks(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    status_filter: Optional[str] = Query(None, description="Filter subtasks by status"),
) -> Dict[str, Any]:
    return handle_get_subtasks(task_id, service, status_filter)


@router.post("/tasks/{task_id}/decompose")
async def decompose_task(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    payload: Dict[str, Any] = None,
) -> Dict[str, Any]:
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    force_decompose = payload.get("force_decompose", False) if payload else False
    if task.task_type != TaskType.MISSION and not force_decompose:
        raise HTTPException(status_code=400, detail="Only mission tasks can be decomposed.")
    
    await service.decompose_and_dispatch_mission(task)
    return {"message": "Task decomposition initiated", "task_id": task_id, "subtask_count": len(task.subtask_ids)}


@router.get("/tasks/{task_id}/execution-history")
async def get_execution_history(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
) -> Dict[str, Any]:
    return handle_get_execution_history(task_id, service)


@router.websocket("/tasks/stream")
async def stream_task_updates(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        service: TaskManagementService = get_task_service(type('obj', (object,), {'app': websocket.app})())
        if service is None:
            raise RuntimeError("Service missing")
    except Exception:
        logger.exception("Task stream initialization failed")
        await websocket.close(code=1011, reason="Task service is not available")
        return
    
    last_task_count = len(service.list_tasks())
    last_revision = service.revision

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1.0)
                if message.get("type") == "websocket.disconnect":
                    return
            except asyncio.TimeoutError:
                continue

            current_tasks = service.list_tasks()
            current_count = len(current_tasks)
            current_revision = service.revision

            if current_count != last_task_count or current_revision != last_revision:
                await websocket.send_json({
                    "type": "task_update",
                    "tasks": [task.model_dump(mode="json") for task in current_tasks],
                    "count": current_count,
                    "timestamp": asyncio.get_event_loop().time(),
                })
                last_task_count = current_count
                last_revision = current_revision
    except WebSocketDisconnect:
        logger.info("Task websocket disconnected")
    except Exception:
        # Do not silently drop runtime stream failures. That would make the task
        # stream look merely idle while the websocket loop has already died.
        logger.exception("Task stream runtime failure")
    finally:
        try:
            await websocket.close()
        except Exception:
            logger.exception("Failed to close task websocket cleanly")


@router.get("/tasks/tree/{task_id}")
async def get_task_tree(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
) -> Dict[str, Any]:
    try:
        return service.get_dependency_tree(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/negotiations")
async def list_negotiations(
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
) -> List[Any]:
    service.trigger_negotiation_scans()
    return list(service.negotiation_generator._active_negotiations.values())


@router.post("/tasks/{task_id}/intervene")
async def intervene_task(
    task_id: str,
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    request: Request,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    try:
        action = str(payload.get("action") or "").strip()
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        remarks = payload.get("remarks")
        operator_id = str(payload.get("operator_id") or (request.client.host if request.client else "unknown"))
        
        # Validation for clinical test suite
        if not action:
            raise HTTPException(status_code=400, detail="action is required")
            
        return await service.intervene(
            task_id, 
            action=action, 
            idempotency_key=idempotency_key or f"manual-{uuid4().hex[:8]}", 
            remarks=str(remarks) if remarks else None, 
            operator_id=operator_id
        )
    except (TaskStateError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=400 if not isinstance(exc, KeyError) else 404, detail=str(exc)) from exc


@router.post("/tasks/bulk-operation")
async def bulk_operation(
    service: Annotated[TaskManagementService, Depends(_require_task_service)],
    request: Request,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    task_ids = payload.get("task_ids", [])
    action = payload.get("action", "")
    remarks = payload.get("remarks", "")
    if not task_ids:
        raise HTTPException(status_code=400, detail="task_ids is required")
    return handle_bulk_operation(service, task_ids, action, remarks)
