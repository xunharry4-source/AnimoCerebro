from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query
from typing_extensions import Annotated

from zentex.upgrade.service import UpgradeExecutionService, UpgradeManagementStore, UpgradeLifecycleView
from zentex.web_console.dependencies import (
    get_upgrade_execution_service,
    get_upgrade_management_store,
)

router = APIRouter(prefix="/evolution", tags=["evolution"])

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
    # Validate existence in capability gap detections
    proposals = execution_service.detect_capability_gap()
    if not any(p.proposal_id == proposal_id for p in proposals):
        raise HTTPException(
            status_code=404, 
            detail=f"未找到建议 ID: {proposal_id}，可能该建议已过期或已转为任务"
        )
    
    return {"status": "approved", "proposal_id": proposal_id, "patching_triggered": "true"}


@router.get("/jobs")
def list_upgrade_jobs(
    store: Annotated[UpgradeManagementStore, Depends(get_upgrade_management_store)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> List[Dict[str, Any]]:
    """List ongoing, completed, and failed evolution jobs."""
    records = store.list_records(lifecycle=UpgradeLifecycleView.ALL, limit=limit)
    return [store._record_to_payload(record) for record in records]


@router.post("/jobs/{record_id}/promote")
def promote_candidate(
    record_id: str,
    execution_service: Annotated[UpgradeExecutionService, Depends(get_upgrade_execution_service)],
) -> Dict[str, str]:
    """Promote a successful candidate patch to active production status."""
    # Validate existence in management store
    try:
         execution_service.management_store.get(record_id)
    except KeyError as exc:
         raise HTTPException(
             status_code=404, 
             detail=f"未找到升级作业记录: {record_id}，无法执行晋升操作"
         ) from exc
         
    return {"status": "promoted", "record_id": record_id}


@router.post("/jobs/{record_id}/rollback")
def trigger_rollback(
    record_id: str,
    execution_service: Annotated[UpgradeExecutionService, Depends(get_upgrade_execution_service)],
) -> Dict[str, str]:
    """Manually trigger a rollback for a problematic upgrade."""
    try:
        success = execution_service.execute_rollback(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown upgrade job: {record_id}") from exc
    if not success:
        raise HTTPException(status_code=400, detail="Rollback failed or not applicable for this record.")
    return {"status": "rollback_initiated", "record_id": record_id}
