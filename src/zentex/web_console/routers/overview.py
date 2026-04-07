from __future__ import annotations

from fastapi import APIRouter, Request
from typing_extensions import Annotated
from fastapi import Depends

from zentex.runtime.runtime import BrainRuntime
from zentex.web_console.contracts.runtime import LLMStatusPayload, RuntimeOverviewPayload
from zentex.web_console.dependencies import get_active_session, get_runtime, get_weight_assembler
from zentex.web_console.services.llm import compute_llm_status
from zentex.web_console.services.overview import build_overview_payload


router = APIRouter()


@router.get("/overview", response_model=RuntimeOverviewPayload)
def get_overview(
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
    request: Request,
) -> RuntimeOverviewPayload:
    session = get_active_session(request)
    return build_overview_payload(runtime, session, get_weight_assembler(request.app))


@router.get("/llm/status", response_model=LLMStatusPayload)
def get_llm_status(request: Request, probe_live: bool = False) -> LLMStatusPayload:
    return compute_llm_status(request, probe_live=probe_live)
