from typing import Optional


from fastapi import APIRouter, HTTPException, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.web_console.contracts.replay import TraceReplayPayload, TurnReplayPayload


router = APIRouter()


@router.get("/replay/{event_id}", response_model=TraceReplayPayload)
def get_replay_trace(
    event_id: str,
    request: Request,
    include_payload: bool = True,
) -> TraceReplayPayload:
    try:
        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service is None:
            raise RuntimeError("audit service unavailable")
        return audit_service.build_trace_replay(event_id, include_payload=include_payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/replay/turn/{turn_id}", response_model=TurnReplayPayload)
def get_turn_replay(
    turn_id: str,
    request: Request,
    session_id: Optional[str] = None,
    include_payload: bool = True,
) -> TurnReplayPayload:
    try:
        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service is None:
            raise RuntimeError("audit service unavailable")
        return audit_service.build_turn_replay(
            turn_id=turn_id,
            session_id=session_id,
            include_payload=include_payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
