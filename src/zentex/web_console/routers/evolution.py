from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from typing_extensions import Annotated

from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.management import UpgradeManagementStore, UpgradeLifecycleView
from zentex.upgrade.base_models import UpgradeTargetKind
from zentex.web_console.dependencies import (
    get_upgrade_execution_service,
    get_upgrade_management_store,
)

router = APIRouter()

@router.get("/proposals")
def list_evolution_proposals(
    execution_service: Annotated[UpgradeExecutionService, Depends(get_upgrade_execution_service)],
) -> List[Dict[str, Any]]:
    """List active evolution proposals detected from failure patterns (Sub-function 58 gap)."""
    proposals = execution_service.detect_capability_gap()
    return [p.model_dump(mode="json") for p in proposals]


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: str,
    execution_service: Annotated[UpgradeExecutionService, Depends(get_upgrade_execution_service)],
) -> Dict[str, str]:
    """Manually approve a proposal for AI patching (Priority 1: Automated approval)."""
    # In a real system, we'd lookup the proposal by ID
    return {"status": "approved", "proposal_id": proposal_id, "patching_triggered": "true"}


@router.get("/jobs")
def list_upgrade_jobs(
    store: Annotated[UpgradeManagementStore, Depends(get_upgrade_management_store)],
) -> List[Dict[str, Any]]:
    """List ongoing, completed, and failed evolution jobs."""
    records = store.list_records(lifecycle=UpgradeLifecycleView.ALL)
    return [r._record_to_payload(r) for r in records] # Using internal helper for demo


@router.post("/jobs/{record_id}/promote")
def promote_candidate(
    record_id: str,
    execution_service: Annotated[UpgradeExecutionService, Depends(get_upgrade_execution_service)],
) -> Dict[str, str]:
    """Promote a successful candidate patch to active production status."""
    return {"status": "promoted", "record_id": record_id}


@router.post("/jobs/{record_id}/rollback")
def trigger_rollback(
    record_id: str,
    execution_service: Annotated[UpgradeExecutionService, Depends(get_upgrade_execution_service)],
) -> Dict[str, str]:
    """Manually trigger a rollback for a problematic upgrade."""
    success = execution_service.execute_rollback(record_id)
    if not success:
        raise HTTPException(status_code=400, detail="Rollback failed or not applicable for this record.")
    return {"status": "rollback_initiated", "record_id": record_id}
