from __future__ import annotations
from typing import Optional


from fastapi import APIRouter, HTTPException
from typing_extensions import Annotated
from fastapi import Depends

from zentex.runtime.runtime import BrainRuntime
from zentex.web_console.contracts.replay import TranscriptReplayPayload, TurnReplayPayload
from zentex.web_console.dependencies import get_runtime
from zentex.web_console.replay_builder import build_replay_payload, build_turn_replay_payload


router = APIRouter()


@router.get("/replay/{event_id}", response_model=TranscriptReplayPayload)
def get_replay_trace(
    event_id: str,
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
    include_payload: bool = True,
) -> TranscriptReplayPayload:
    try:
        return build_replay_payload(runtime, event_id, include_payload=include_payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/replay/turn/{turn_id}", response_model=TurnReplayPayload)
def get_turn_replay(
    turn_id: str,
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
    session_id: Optional[str] = None,
    include_payload: bool = True,
) -> TurnReplayPayload:
    try:
        return build_turn_replay_payload(
            runtime,
            turn_id=turn_id,
            session_id=session_id,
            include_payload=include_payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

