from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from typing_extensions import Annotated

from zentex.web_console.dependencies import get_runtime, get_task_service
from zentex.runtime.runtime import BrainRuntime

router = APIRouter(prefix="/governance", tags=["governance"])
logger = logging.getLogger(__name__)

@router.get("/status")
async def get_governance_status(
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
    task_service: Annotated[Any, Depends(get_task_service)],
) -> Dict[str, Any]:
    """
    Get the top-level governance and system integrity status.
    """
    # System Health
    memory_status = runtime.runtime_memory_store.get_storage_stats() if hasattr(runtime.runtime_memory_store, "get_storage_stats") else {}
    
    # Task stats
    task_stats = task_service.get_task_statistics()
    
    # Identity lock status
    identity_verified = getattr(runtime.state, "identity_verified", False)
    
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
    runtime: Annotated[BrainRuntime, Depends(get_runtime)],
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
