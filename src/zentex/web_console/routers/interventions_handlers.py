from __future__ import annotations
"""
Intervention Route Handlers — Business logic for manual interventions.
Extracted from interventions.py to follow the Facade-First / Thin-Route pattern.
"""
from typing import Any, Dict
from fastapi import HTTPException, Request
from zentex.web_console.contracts.interventions import InterventionRequest
from zentex.web_console.services.interventions import post_intervention as run_intervention


async def handle_post_intervention(
    payload: InterventionRequest,
    facade: Any,
    request: Request,
) -> Dict[str, Any]:
    """Handle posting a manual intervention."""
    # Attempt to find a runtime-like object for legacy service support
    runtime_source = getattr(request.app.state, "runtime", None)
    audit_service = getattr(request.app.state, "audit_service", None)
    
    # If no legacy runtime, check if facade can provide equivalent functionality
    # (Future-proofing: facade might eventually wrap intervention logic)
    
    if runtime_source is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "runtime_not_attached",
                "message": "Runtime 未注入 app.state，或者 KernelService 尚未完全支持此干预操作。",
            },
        )
        
    return await run_intervention(
        payload,
        runtime_source,
        audit_service,
        facade.get_session_manager(),
        request,
    )
