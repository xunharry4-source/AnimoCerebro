"""
Interventions Router — POST /api/web/interventions.

RESPONSIBILITY:
  Accepts human-intervention requests (e.g. override, correction, directive)
  and forwards them to the intervention service for runtime application.
"""

from __future__ import annotations

from typing_extensions import Annotated
from fastapi import APIRouter, Depends, Request

from zentex.web_console.contracts.interventions import InterventionRequest
from zentex.web_console.contracts.kernel_service import KernelServiceFacade
from zentex.web_console.dependencies import get_kernel_service_facade
from .interventions_handlers import handle_post_intervention


router = APIRouter()


@router.post("/interventions")
async def post_intervention(
    payload: InterventionRequest,
    facade: Annotated[KernelServiceFacade, Depends(get_kernel_service_facade)],
    request: Request,
) -> dict:
    """Post a manual intervention request."""
    return await handle_post_intervention(payload, facade, request)
