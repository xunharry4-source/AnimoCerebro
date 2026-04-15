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
    """
    Phase F: Get detailed explanation of dispatch routing decision.
    
    Returns why a specific executor was selected for this task,
    including all candidates evaluated and ranking rationale.
    """
    try:
        # TODO: Retrieve task and dispatch history from service
        # For now, return a mock explanation
        
        explanation = DispatchExplanation(
            task_id=task_id,
            task_type="cognitive_step",
            selected_executor_id="executor-1",
            selected_executor_name="Internal Plugin: LLM Orchestrator",
            selection_rationale="Highest capability match (0.95) and best historical success rate (0.92)",
            confidence=0.95,
            all_candidates=[
                ExecutorCandidateExplanation(
                    executor_id="executor-1",
                    executor_type="internal_plugin",
                    name="LLM Orchestrator",
                    is_healthy=True,
                    capability_match_score=0.95,
                    credit_score=9.0,
                    experience_success_rate=0.92,
                    selection_reason="Best match for task type",
                    was_selected=True,
                    ranking_position=1,
                    fallback_chain_position=0,
                ),
                ExecutorCandidateExplanation(
                    executor_id="executor-2",
                    executor_type="mcp_agent",
                    name="External MCP Agent",
                    is_healthy=True,
                    capability_match_score=0.75,
                    credit_score=6.5,
                    experience_success_rate=0.68,
                    selection_reason="Lower capability match, kept as fallback",
                    was_selected=False,
                    ranking_position=2,
                    fallback_chain_position=1,
                ),
            ],
            candidates_rejected_count=1,
            rejection_reasons=["Health check failed"],
            internal_plugins_checked=3,
            internal_plugins_matched=2,
            external_agents_checked=2,
            routing_algorithm="UnifiedTaskRouter v1",
        )
        
        return explanation
        
    except Exception as e:
        logger.error(f"Failed to get dispatch explanation for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/dispatch-candidates")
async def list_dispatch_candidates(
    task_id: str,
    status_filter: Optional[str] = Query(None, description="selected, fallback, rejected"),
):
    """
    Phase F: List all dispatch candidates for a task with their scores.
    """
    try:
        # TODO: Get candidates from dispatch history
        candidates = [
            {
                "executor_id": "executor-1",
                "name": "LLM Orchestrator",
                "type": "internal_plugin",
                "status": "selected",
                "credit_score": 9.0,
                "capability_match": 0.95,
                "success_rate": 0.92,
            },
            {
                "executor_id": "executor-2",
                "name": "External MCP Agent",
                "type": "mcp_agent",
                "status": "fallback",
                "credit_score": 6.5,
                "capability_match": 0.75,
                "success_rate": 0.68,
            },
        ]
        
        if status_filter:
            candidates = [c for c in candidates if c["status"] == status_filter]
        
        return {"task_id": task_id, "candidates": candidates}
        
    except Exception as e:
        logger.error(f"Failed to list dispatch candidates for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VERIFICATION RESULTS DETAIL ENDPOINTS
# ============================================================================

@router.get("/tasks/{task_id}/verification-details", response_model=VerificationDetailExplanation)
async def get_verification_details(task_id: str):
    """
    Phase F: Get detailed verification results including failure classification.
    
    Returns failure type, severity, evidence, lessons learned, and
    recommended actions from verification process.
    """
    try:
        # TODO: Retrieve verification history from service
        # For now, return a mock result
        
        details = VerificationDetailExplanation(
            task_id=task_id,
            verification_passed=False,
            verification_score=0.45,
            failure_type="executor_timeout",
            failure_severity="HIGH",
            failure_evidence="Task exceeded 300s timeout threshold, no partial output received",
            lessons_learned=[
                "This task type typically requires 150-250 seconds",
                "Network latency can add 50s+ to execution time",
                "Consider increasing timeout for this executor",
            ],
            recommended_actions=[
                "Retry with increased timeout (450s instead of 300s)",
                "Consider fallback to LLM-based executor",
                "Escalate to human operator if retries exhaust",
            ],
            confidence_in_recommendations=0.85,
        )
        
        return details
        
    except Exception as e:
        logger.error(f"Failed to get verification details for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/verification-history")
async def get_verification_history(task_id: str):
    """
    Phase F: Get complete verification history (all checks performed).
    """
    try:
        # TODO: Get verification history from service
        history = {
            "task_id": task_id,
            "verifications": [
                {
                    "timestamp": "2026-04-12T10:30:00Z",
                    "check_type": "output_structure_check",
                    "passed": True,
                    "details": "Output contained expected JSON structure",
                },
                {
                    "timestamp": "2026-04-12T10:30:05Z",
                    "check_type": "timeout_check",
                    "passed": False,
                    "details": "Execution time 305s exceeded threshold of 300s",
                },
            ],
            "overall_passed": False,
        }
        
        return history
        
    except Exception as e:
        logger.error(f"Failed to get verification history for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SUPERVISION HISTORY ENDPOINTS
# ============================================================================

@router.get("/tasks/{task_id}/supervision-history", response_model=SupervisionHistoryExplanation)
async def get_supervision_history(task_id: str):
    """
    Phase F: Get complete supervision chain for a task.
    
    Returns all supervision decisions, actions taken, and their outcomes
    in chronological order.
    """
    try:
        # TODO: Retrieve supervision history from service
        # For now, return a mock history
        
        history = SupervisionHistoryExplanation(
            task_id=task_id,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            supervision_actions=[
                SupervisionActionExplanation(
                    task_id=task_id,
                    action_type="RETRY",
                    action_reason="Timeout detected; task may complete with extended time",
                    trigger_failure_type="executor_timeout",
                    action_executed=True,
                    action_result="Task completed successfully after retry",
                    next_action_if_fails="FALLBACK",
                    estimated_recovery_time=150,
                ),
            ],
            total_attempts=1,
            supervision_successful=True,
            final_status="SUCCESS",
            observations=[
                "First retry succeeded within extended timeout",
                "Executor exhibited temporary latency spike",
                "Credit score will be maintained (not penalized)",
            ],
        )
        
        return history
        
    except Exception as e:
        logger.error(f"Failed to get supervision history for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/supervision-actions")
async def list_supervision_actions(
    task_id: str,
    action_type: Optional[str] = Query(None, description="Filter by action type"),
):
    """
    Phase F: List all supervision actions for a task.
    """
    try:
        # TODO: Get supervision actions from service
        actions = [
            {
                "action_id": "action-001",
                "action_type": "RETRY",
                "timestamp": "2026-04-12T10:30:10Z",
                "reason": "Executor timeout; retrying with extended threshold",
                "status": "succeeded",
                "result": "Task completed successfully",
            },
        ]
        
        if action_type:
            actions = [a for a in actions if a["action_type"] == action_type]
        
        return {"task_id": task_id, "actions": actions}
        
    except Exception as e:
        logger.error(f"Failed to list supervision actions for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SUMMARY/DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/tasks/{task_id}/observability-summary")
async def get_observability_summary(task_id: str):
    """
    Phase F: Get complete observability summary (dispatch + verification + supervision).
    
    Useful for dashboard displays showing full task lifecycle.
    """
    try:
        summary = {
            "task_id": task_id,
            "dispatch": {
                "selected_executor": "Internal Plugin: LLM Orchestrator",
                "confidence": 0.95,
                "candidates_evaluated": 2,
            },
            "verification": {
                "status": "failed",
                "failure_type": "executor_timeout",
                "severity": "HIGH",
            },
            "supervision": {
                "status": "completed",
                "actions_taken": 1,
                "final_outcome": "success",
            },
            "timeline": [
                {"event": "dispatch_start", "timestamp": "2026-04-12T10:30:00Z"},
                {"event": "verification_failed", "timestamp": "2026-04-12T10:30:05Z"},
                {"event": "supervision_start", "timestamp": "2026-04-12T10:30:05Z"},
                {"event": "retry_action", "timestamp": "2026-04-12T10:30:10Z"},
                {"event": "task_complete", "timestamp": "2026-04-12T10:31:45Z"},
            ],
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get observability summary for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/observability/health")
async def observability_health():
    """
    Phase F: Health check for observability services.
    """
    return {
        "status": "healthy",
        "endpoints": [
            "dispatch-explanation",
            "verification-details",
            "supervision-history",
            "observability-summary",
        ],
    }
