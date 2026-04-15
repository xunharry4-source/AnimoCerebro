"""
Overview Commons Module — runtime overview query helpers.

RESPONSIBILITY:
  Provides async query helpers used by overview.py route handlers.
  Does NOT own any routes or app state; it only reads from request.app.state.

CAPABILITIES:
  - query_runtime_overview(): assembles RuntimeOverviewPayload from app.state.runtime
  - query_llm_status(): reads LLM provider availability

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  - If app.state.runtime is None → 503 (runtime not attached).
  - If build_overview_payload raises → 500 with structured error detail.
  - No silent stub, no empty fallback payload, no swallowed exceptions.

DOES NOT:
  - Own app state or the runtime object itself.
  - Fall back to synthetic/empty cognitive state when runtime is unavailable.
"""

from typing import Any, Optional
import logging

from fastapi import HTTPException, Request
from zentex.web_console.contracts.runtime import LLMStatusPayload, RuntimeOverviewPayload
from zentex.web_console.dependencies import get_weight_assembler
from zentex.web_console.services.llm import compute_llm_status
from zentex.web_console.services.overview import build_overview_payload

logger = logging.getLogger(__name__)


async def query_runtime_overview(
    request: Request,
    facade: Optional[Any] = None
) -> RuntimeOverviewPayload:
    """Query current runtime overview state.

    Raises:
        HTTPException 503: kernel service not available.
        HTTPException 500: build failed.

    Returns:
        RuntimeOverviewPayload with current system state.
    """
    from zentex.web_console.dependencies import get_kernel_service_facade, get_weight_assembler
    
    # Use provided facade or derive from request state.
    if facade is None:
        facade = get_kernel_service_facade(request)

    # Get additional services
    foundation = getattr(request.app.state, 'foundation_service', None)
    
    # Identify the primary active session
    active_sessions = facade.list_active_sessions()
    session_id = active_sessions[0] if active_sessions else "web-console"

    try:
        # Build payload using facade and specific services
        overview = build_overview_payload(
            facade=facade,
            foundation=foundation,
            session_id=session_id,
            weight_assembler=get_weight_assembler(request.app),
        )
    except Exception as exc:
        logger.error("overview: build_overview_payload failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "overview_build_failed",
                "message": f"构建 overview payload 失败：{type(exc).__name__}: {exc}",
            },
        ) from exc

    logger.info("overview: runtime overview retrieved successfully")
    return overview


async def query_llm_status(
    request: Request,
    probe_live: bool = False
) -> LLMStatusPayload:
    """Query current LLM status
    
    Args:
        request: FastAPI request
        probe_live: Whether to probe live LLM status (may be slow)
        
    Returns:
        LLMStatusPayload with status information
    """
    try:
        status = compute_llm_status(request, probe_live=probe_live)
        logger.info(f"LLM status retrieved (probe_live={probe_live})")
        return status
    except Exception as e:
        logger.error(f"Failed to query LLM status: {e}")
        raise RuntimeError(f"LLM status query failed: {str(e)}")
