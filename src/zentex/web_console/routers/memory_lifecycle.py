from __future__ import annotations

"""Web API for memory lifecycle governance."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from zentex.memory.service import MemoryService, get_memory_service


router = APIRouter(prefix="/memory-lifecycle/g39", tags=["memory-lifecycle-g39"])


class LifecycleCycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = "api"
    now: datetime | None = None


class LifecycleCompactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_ids: list[str]
    summary: str
    operator: str = "api"


class LifecycleRewarmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    operator: str = "api"


class LifecycleContaminationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    operator: str = "api"


def _service(request: Request) -> MemoryService:
    service = getattr(request.app.state, "memory_service", None)
    if service is None:
        service = get_memory_service()
        request.app.state.memory_service = service
    return service


@router.post("/cycles")
def run_lifecycle_cycle(payload: LifecycleCycleRequest, request: Request) -> dict[str, object]:
    report = _service(request).run_memory_lifecycle_cycle(operator=payload.operator, now=payload.now)
    return report.model_dump(mode="json")


@router.get("/cycles")
def list_lifecycle_cycles(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_memory_lifecycle_cycles()]


@router.get("/recall")
def recall_lifecycle_memory(request: Request, query: str = Query(min_length=1), limit: int = 10) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).recall_memory_lifecycle(query, limit=limit)]


@router.post("/compactions")
def compress_lifecycle_memories(payload: LifecycleCompactionRequest, request: Request) -> dict[str, object]:
    try:
        report = _service(request).compress_lifecycle_memories(
            payload.memory_ids,
            summary=payload.summary,
            operator=payload.operator,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found", "memory_id": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    return report.model_dump(mode="json")


@router.get("/compactions")
def list_lifecycle_compactions(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_memory_lifecycle_compactions()]


@router.post("/memories/{memory_id}/rewarm")
def rewarm_lifecycle_memory(memory_id: str, payload: LifecycleRewarmRequest, request: Request) -> dict[str, object]:
    try:
        state = _service(request).rewarm_lifecycle_memory(memory_id, operator=payload.operator, reason=payload.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    return state.model_dump(mode="json")


@router.post("/memories/{memory_id}/contamination")
def mark_lifecycle_memory_contaminated(
    memory_id: str,
    payload: LifecycleContaminationRequest,
    request: Request,
) -> dict[str, object]:
    try:
        state = _service(request).mark_lifecycle_memory_contaminated(
            memory_id,
            reason=payload.reason,
            operator=payload.operator,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found"}) from exc
    return state.model_dump(mode="json")


@router.post("/compactions/{compressed_memory_id}/restore")
def restore_lifecycle_compressed_chain(compressed_memory_id: str, request: Request) -> list[dict[str, object]]:
    try:
        states = _service(request).restore_lifecycle_compressed_chain(compressed_memory_id, operator="api")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found"}) from exc
    return [row.model_dump(mode="json") for row in states]


@router.get("/states")
def list_lifecycle_states(request: Request) -> list[dict[str, object]]:
    return [row.model_dump(mode="json") for row in _service(request).list_memory_lifecycle_states()]
