"""
Phase F: Observability Router

Exposes dispatch route explanations, verification details, and supervision
history through REST APIs for frontend and external observers.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from zentex.tasks import get_service
from zentex.web_console.models_observability import (
    DispatchExplanation,
    VerificationDetailExplanation,
    SupervisionHistoryExplanation,
    SupervisionActionExplanation,
    ExecutorCandidateExplanation,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"])


# ============================================================================
# DISPATCH ROUTING EXPLANATION ENDPOINTS
# ============================================================================

@router.get("/tasks/{task_id}/dispatch-explanation", response_model=DispatchExplanation)
async def get_dispatch_explanation(
    task_id: str,
    include_all_candidates: bool = Query(True, description="Include all candidates or just selected?"),
):
    # Phase F: Get detailed explanation of dispatch routing decision.
    service = get_service()
    records = service.get_dispatch_records(task_id)
    
    if not records:
        return DispatchExplanation(
            task_id=task_id,
            selected_executor_id=None,
            reasoning="No dispatch audit records found for this task. (Historical data might not be available for tasks started before Phase F restoration).",
            candidates=[]
        )
    
    # Use newest record
    record = records[-1]
    
    candidates = []
    if include_all_candidates:
        for c in record.get("candidate_pool", []):
            candidates.append(ExecutorCandidateExplanation(
                executor_id=c.get("executor_id"),
                executor_name=c.get("executor_name"),
                executor_type=c.get("executor_type"),
                score=c.get("capability_match_score", 0.0),
                is_healthy=c.get("is_healthy", True),
                reason=c.get("routing_reason", "")
            ))
            
    selected = record.get("selected_executor")
    selected_id = selected.get("executor_id") if selected else None
    
    return DispatchExplanation(
        task_id=task_id,
        selected_executor_id=selected_id,
        reasoning=record.get("decision_logic", "unknown_logic"),
        candidates=candidates
    )


@router.get("/tasks/{task_id}/dispatch-candidates")
async def list_dispatch_candidates(
    task_id: str,
    status_filter: Optional[str] = Query(None, description="selected, fallback, rejected"),
):
    # Phase F: List all dispatch candidates for a task with their scores.
    service = get_service()
    records = service.get_dispatch_records(task_id)
    if not records:
        return []
        
    record = records[-1]
    candidates = record.get("candidate_pool", [])
    
    # Simple filtering if requested
    if status_filter == "selected":
        selected_id = record.get("selected_executor", {}).get("executor_id")
        candidates = [c for c in candidates if c.get("executor_id") == selected_id]
        
    return candidates


# ============================================================================
# VERIFICATION RESULTS DETAIL ENDPOINTS
# ============================================================================

@router.get("/tasks/{task_id}/verification-details", response_model=VerificationDetailExplanation)
async def get_verification_details(task_id: str):
    # Phase F: Get detailed verification results including failure classification.
    service = get_service()
    records = service.get_verification_records(task_id)
    
    if not records:
        raise HTTPException(status_code=404, detail=f"No verification details found for task {task_id}.")
        
    # Get latest result
    record = records[-1]
    
    return VerificationDetailExplanation(
        task_id=task_id,
        verification_status=record.get("overall_status", "unknown"),
        check_count=record.get("verifier_count", 0),
        failed_checks=[r.get("verifier_id") for r in record.get("verifier_results", []) if not r.get("passed")],
        passed_checks=[r.get("verifier_id") for r in record.get("verifier_results", []) if r.get("passed")]
    )


@router.get("/tasks/{task_id}/verification-history")
async def get_verification_history(task_id: str):
    # Phase F: Get complete verification history (all checks performed).
    service = get_service()
    return service.get_verification_records(task_id)


# ============================================================================
# SUPERVISION HISTORY ENDPOINTS
# ============================================================================

@router.get("/tasks/{task_id}/supervision-history", response_model=SupervisionHistoryExplanation)
async def get_supervision_history(task_id: str):
    # Phase F: Get complete supervision chain for a task.
    service = get_service()
    records = service.get_supervision_records(task_id)
    
    actions = []
    for r in records:
        actions.append(SupervisionActionExplanation(
            action_type=r.get("action", "unknown"),
            timestamp=r.get("timestamp"),
            performed_by="system_observability",
            remarks=str(r.get("details", ""))
        ))
        
    return SupervisionHistoryExplanation(
        task_id=task_id,
        supervision_status="active" if actions else "not_supervised",
        actions=actions
    )


@router.get("/tasks/{task_id}/supervision-actions")
async def list_supervision_actions(
    task_id: str,
    action_type: Optional[str] = Query(None, description="Filter by action type"),
):
    # Phase F: List all supervision actions for a task.
    service = get_service()
    records = service.get_supervision_records(task_id)
    if action_type:
        records = [r for r in records if r.get("action") == action_type]
    return records


# ============================================================================
# SUMMARY/DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/tasks/{task_id}/observability-summary")
async def get_observability_summary(task_id: str):
    # Phase F: Get complete observability summary (dispatch + verification + supervision).
    service = get_service()
    
    dispatch = service.get_dispatch_records(task_id)
    verification = service.get_verification_records(task_id)
    supervision = service.get_supervision_records(task_id)
    
    return {
        "task_id": task_id,
        "dispatch": dispatch[-1] if dispatch else None,
        "verification": verification[-1] if verification else None,
        "supervision_count": len(supervision),
        "status": "ready" if (dispatch or verification or supervision) else "data_unavailable"
    }

