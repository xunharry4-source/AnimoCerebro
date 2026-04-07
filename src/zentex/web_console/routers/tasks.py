from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.tasks.models import ZentexTask
from zentex.tasks.service import TaskManagementService
from zentex.tasks.errors import TaskStateError
from zentex.web_console.dependencies import get_task_service


router = APIRouter()


@router.get("/tasks", response_model=List[ZentexTask])
async def list_tasks(
    service: Annotated[TaskManagementService, Depends(get_task_service)],
) -> List[ZentexTask]:
    return service.list_tasks()


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

