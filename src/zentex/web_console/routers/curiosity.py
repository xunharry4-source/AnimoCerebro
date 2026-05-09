from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from zentex.cognition.curiosity import (
    CuriosityBudget,
    CuriosityCycleReport,
    CuriosityEngine,
    CuriosityTask,
    EpistemicUncertainty,
    ExplorationResult,
    get_curiosity_engine,
)


router = APIRouter()


class CuriosityCycleRequest(BaseModel):
    uncertainties: list[EpistemicUncertainty] = Field(default_factory=list)
    budget: CuriosityBudget
    active_external_task_count: int = Field(default=0, ge=0)
    trigger_source: str = "idle_heartbeat"


class ExplorationResultRequest(BaseModel):
    findings: str = Field(min_length=1)
    confidence_delta: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)


def _get_engine(request: Request) -> CuriosityEngine:
    engine = getattr(request.app.state, "curiosity_engine", None)
    if engine is not None:
        return engine
    engine = get_curiosity_engine()
    request.app.state.curiosity_engine = engine
    return engine


def _get_memory_service(request: Request) -> Any:
    memory_service = getattr(request.app.state, "memory_service", None)
    if memory_service is not None:
        return memory_service
    from zentex.memory.service import get_memory_service

    memory_service = get_memory_service()
    request.app.state.memory_service = memory_service
    return memory_service


@router.post("/curiosity/cycles")
def run_curiosity_cycle(payload: CuriosityCycleRequest, request: Request) -> CuriosityCycleReport:
    try:
        trigger_source = payload.trigger_source
        if trigger_source not in {"idle_heartbeat", "manual_cycle"}:
            raise ValueError("trigger_source must be idle_heartbeat or manual_cycle")
        return _get_engine(request).run_idle_cycle(
            uncertainties=payload.uncertainties,
            budget=payload.budget,
            active_external_task_count=payload.active_external_task_count,
            trigger_source=trigger_source,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/curiosity/tasks")
def list_curiosity_tasks(request: Request) -> list[CuriosityTask]:
    return _get_engine(request).list_tasks()


@router.get("/curiosity/tasks/{task_id}")
def get_curiosity_task(task_id: str, request: Request) -> CuriosityTask:
    task = _get_engine(request).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"CuriosityTask {task_id} not found")
    return task


@router.post("/curiosity/tasks/{task_id}/results")
def complete_curiosity_task(task_id: str, payload: ExplorationResultRequest, request: Request) -> ExplorationResult:
    try:
        return _get_engine(request).complete_task(
            task_id=task_id,
            findings=payload.findings,
            confidence_delta=payload.confidence_delta,
            evidence_refs=payload.evidence_refs,
            memory_service=_get_memory_service(request),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/curiosity/tasks/{task_id}/memory-record")
def get_curiosity_task_memory(task_id: str, request: Request) -> dict[str, Any]:
    task = _get_engine(request).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"CuriosityTask {task_id} not found")
    if not task.memory_id:
        raise HTTPException(status_code=404, detail=f"CuriosityTask {task_id} has no memory record")
    record = _get_memory_service(request).get_record(task.memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Memory record {task.memory_id} not found")
    return {
        "task_id": task_id,
        "memory_id": task.memory_id,
        "title": getattr(record, "title", None),
        "summary": getattr(record, "summary", None),
        "content": getattr(record, "content", None),
        "source": getattr(record, "source_kind", None),
        "trace_id": getattr(record, "trace_id", None),
        "target_id": getattr(record, "target_id", None),
        "tags": list(getattr(record, "tags", []) or []),
    }
