"""Web API for G31A autonomous control loop."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from zentex.autonomy.autonomous_loop import AutonomousControlLoop, Stimulus

router = APIRouter(prefix="/autonomous-loop", tags=["autonomous-loop"])


class CycleRequest(BaseModel):
    """Autonomous cycle request."""

    model_config = ConfigDict(extra="forbid")

    budget_level: str = "normal"


class TransitionRequest(BaseModel):
    """Task transition request."""

    model_config = ConfigDict(extra="forbid")

    action: str
    reason: str


def _loop(request: Request) -> AutonomousControlLoop:
    loop = getattr(request.app.state, "autonomous_control_loop", None)
    if loop is None:
        loop = AutonomousControlLoop()
        request.app.state.autonomous_control_loop = loop
    return loop


@router.post("/stimuli")
def ingest_stimulus(payload: Stimulus, request: Request) -> dict[str, Any]:
    """Persist one stimulus."""

    return _loop(request).ingest_stimulus(payload).model_dump(mode="json")


@router.post("/cycles")
def run_cycle(payload: CycleRequest, request: Request) -> dict[str, Any]:
    """Run one autonomous cycle."""

    return _loop(request).run_cycle(budget_level=payload.budget_level).model_dump(mode="json")


@router.post("/tasks/{task_id}/transition")
def transition_task(task_id: str, payload: TransitionRequest, request: Request) -> dict[str, Any]:
    """Transition a task state."""

    try:
        task = _loop(request).transition_task(task_id, payload.action, reason=payload.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "task_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "illegal_transition", "message": str(exc)}) from exc
    return task.model_dump(mode="json")


@router.get("/tasks")
def list_tasks(request: Request) -> list[dict[str, Any]]:
    """Return autonomous tasks."""

    return [row.model_dump(mode="json") for row in _loop(request).list_tasks()]


@router.get("/audit")
def list_audit(request: Request) -> list[dict[str, Any]]:
    """Return autonomous loop audit events."""

    return _loop(request).list_audit_events()
