from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from zentex.web_console.dependencies import get_kernel_service_facade


router = APIRouter()


class ExternalBrainConsultRequest(BaseModel):
    session_id: str = Field(min_length=1)
    user_input: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    turn_id: str | None = None
    trace_id: str | None = None


@router.post("/external-brain/consult")
def consult_external_brain(
    payload: ExternalBrainConsultRequest,
    facade: Annotated[Any, Depends(get_kernel_service_facade)],
) -> dict[str, Any]:
    try:
        return facade.consult_external_brain(
            session_id=payload.session_id,
            user_input=payload.user_input,
            context=payload.context,
            turn_id=payload.turn_id,
            trace_id=payload.trace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": exc.__class__.__name__, "message": str(exc)}) from exc
