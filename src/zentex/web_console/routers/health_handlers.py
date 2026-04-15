"""
Health Route Handlers — Business logic for system health monitoring.
Extracted from health.py to follow the Facade-First / Thin-Route pattern.
"""
from __future__ import annotations
from typing import Any
from fastapi import Request
from zentex.web_console.contracts.health import SystemHealthPayload
from zentex.web_console.services.health import build_system_health_payload


def handle_get_system_health(
    request: Request,
    managed_records: Any,
    kernel_facade: Any,
) -> SystemHealthPayload:
    """Handle retrieving and assembling system health information."""
    
    # Extract services from app state
    foundation_service = getattr(request.app.state, 'foundation_service', None)
    task_service = getattr(request.app.state, 'task_service', None)
    memory_service = getattr(request.app.state, 'enhanced_memory_service', None)
    
    # Attempt to read LLM gateway stats
    llm_gateway_stats = None
    if foundation_service and hasattr(foundation_service, 'get_llm_gateway_stats'):
        try:
            llm_gateway_stats = foundation_service.get_llm_gateway_stats()
        except Exception:
            pass
            
    return build_system_health_payload(
        managed_records=managed_records,
        llm_gateway_stats=llm_gateway_stats,
        kernel_facade=kernel_facade,
        foundation_service=foundation_service,
        task_service=task_service,
        memory_service=memory_service,
    )
