from __future__ import annotations

from fastapi import APIRouter, Request
from typing_extensions import Annotated
from fastapi import Depends

from typing import Any
from zentex.web_console.contracts.interventions import InterventionRequest
from zentex.web_console.dependencies import get_runtime
from zentex.web_console.services.interventions import post_intervention as run_intervention
from zentex.runtime.runtime import BrainRuntime


router = APIRouter()


@router.post("/interventions")
def post_intervention(
    payload: InterventionRequest,
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
    request: Request,
) -> dict:
    return run_intervention(payload, runtime, request)

