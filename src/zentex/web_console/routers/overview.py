from __future__ import annotations
"""
Overview Router Module (v5)
Runtime overview query endpoints
Facade-First route layer extracted from overview.py
"""


from fastapi import APIRouter, Depends, Request
from typing_extensions import Annotated

from zentex.web_console.contracts.runtime import LLMStatusPayload, RuntimeOverviewPayload
from zentex.web_console.dependencies import get_kernel_service_facade
from .overview_commons import (
    query_runtime_overview,
    query_llm_status,
)

router = APIRouter()


@router.get("/overview", response_model=RuntimeOverviewPayload)
async def get_overview(
    request: Request,
    facade: Annotated[object, Depends(get_kernel_service_facade)],
) -> RuntimeOverviewPayload:
    """
    Get current runtime overview
    
    Includes system state, agent status, inference metrics, etc.
    
    Returns:
        RuntimeOverviewPayload with comprehensive system overview
    """
    return await query_runtime_overview(request, facade)


@router.get("/llm/status", response_model=LLMStatusPayload)
async def get_llm_status(
    request: Request,
    probe_live: bool = False,
) -> LLMStatusPayload:
    """
    Get LLM provider status
    
    Args:
        probe_live: Whether to probe live status (may increase latency)
        
    Returns:
        LLMStatusPayload with provider availability and metrics
    """
    return await query_llm_status(request, probe_live=probe_live)
