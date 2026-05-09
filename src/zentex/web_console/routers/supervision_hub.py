from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from zentex.supervision.hub import ThoughtTrace


router = APIRouter()


class InterventionPayload(BaseModel):
    action: str
    reason: str
    operator_id: str = "human_supervisor"
    confirmation_token: str | None = None


class WriteCheckPayload(BaseModel):
    action_payload: dict[str, Any] = Field(default_factory=dict)


def _get_hub(request: Request):
    hub = getattr(request.app.state, "supervision_hub", None)
    if hub is not None:
        return hub
    from zentex.supervision.hub import get_supervision_hub

    hub = get_supervision_hub()
    request.app.state.supervision_hub = hub
    return hub


@router.get("/supervision-hub/state")
def get_state(request: Request):
    return _get_hub(request).get_state()


@router.post("/supervision-hub/terminals/{terminal_id}/connect")
def connect_terminal(terminal_id: str, request: Request):
    return _get_hub(request).connect_terminal(terminal_id)


@router.post("/supervision-hub/terminals/{terminal_id}/disconnect")
def disconnect_terminal(terminal_id: str, request: Request):
    return _get_hub(request).disconnect_terminal(terminal_id)


@router.post("/supervision-hub/thought-traces")
def append_thought_trace(trace: ThoughtTrace, request: Request) -> ThoughtTrace:
    try:
        return _get_hub(request).append_thought_trace(trace)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/supervision-hub/thought-traces")
def list_thought_traces(request: Request, session_id: str | None = None, after_sequence: int | None = None):
    return _get_hub(request).list_thought_traces(session_id=session_id, after_sequence=after_sequence)


@router.websocket("/supervision-hub/thought-stream")
async def stream_thought_traces(
    websocket: WebSocket,
    session_id: str,
    after_sequence: int = -1,
    terminal_id: str | None = None,
):
    await websocket.accept()
    hub = getattr(websocket.app.state, "supervision_hub", None)
    if hub is None:
        from zentex.supervision.hub import get_supervision_hub

        hub = get_supervision_hub()
        websocket.app.state.supervision_hub = hub
    if terminal_id:
        hub.connect_terminal(terminal_id)

    last_sequence = after_sequence
    try:
        while True:
            traces = hub.list_thought_traces(session_id=session_id, after_sequence=last_sequence)
            for trace in traces:
                await websocket.send_json(trace.model_dump(mode="json"))
                last_sequence = max(last_sequence, trace.sequence)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return
    finally:
        if terminal_id:
            hub.disconnect_terminal(terminal_id)


@router.post("/supervision-hub/interventions")
def apply_intervention(payload: InterventionPayload, request: Request):
    try:
        return _get_hub(request).apply_intervention(
            action=payload.action,
            reason=payload.reason,
            operator_id=payload.operator_id,
            confirmation_token=payload.confirmation_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/supervision-hub/interventions")
def list_interventions(request: Request):
    return _get_hub(request).list_interventions()


@router.post("/supervision-hub/write-check")
def assert_write_allowed(payload: WriteCheckPayload, request: Request):
    hub = _get_hub(request)
    try:
        hub.assert_write_allowed(payload.action_payload)
    except RuntimeError as exc:
        state = hub.get_state()
        raise HTTPException(
            status_code=423,
            detail={
                "error": exc.__class__.__name__,
                "message": str(exc),
                "mode": state.mode.value,
                "write_allowed": state.write_allowed,
            },
        ) from exc
    state = hub.get_state()
    return {
        "mode": state.mode.value,
        "write_allowed": state.write_allowed,
    }
