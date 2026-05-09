from __future__ import annotations

import logging
from typing import Any, Dict
from fastapi import APIRouter, Request

router = APIRouter(prefix="/governance", tags=["governance"])
logger = logging.getLogger(__name__)

@router.get("/status")
async def get_governance_status(
    request: Request,
) -> Dict[str, Any]:
    """
    Get the top-level governance and system integrity status.
    """
    runtime = getattr(request.app.state, "runtime", None)
    task_service = getattr(request.app.state, "task_service", None)

    # System Health
    memory_store = getattr(runtime, "runtime_memory_store", None)
    memory_status = memory_store.get_storage_stats() if hasattr(memory_store, "get_storage_stats") else {}
    
    # Task stats
    task_stats = task_service.get_task_statistics() if hasattr(task_service, "get_task_statistics") else {}
    
    # Identity lock status
    identity_verified = getattr(getattr(runtime, "state", None), "identity_verified", False)
    
    return {
        "system_integrity": {
            "identity_lock": "active" if identity_verified else "warning",
            "autonomy_level": "autonomous",
            "last_heartbeat": "now", # Placeholder
        },
        "resource_governance": {
            "memory_usage": memory_status,
            "quota_remaining": 1.0, # Placeholder
        },
        "task_governance": task_stats,
        "compliance": {
            "g25_rational_audit": "healthy",
            "drift_detected": False
        }
    }

@router.get("/audits/summary")
async def get_audit_summary(
    request: Request,
) -> Dict[str, Any]:
    """
    Get summary of recent audit events.
    """
    # In a real system, this would aggregate PLUGIN_AUDIT_EVENTs from the transcript store
    return {
        "recent_audits": 5,
        "critical_alerts": 0,
        "policy_violations": 0
    }
