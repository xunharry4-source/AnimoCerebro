from __future__ import annotations

"""
Web API routes for AI supervision monitoring and management.

Provides REST endpoints for:
- Viewing supervision status and alerts
- Managing supervision rules
- Human intervention and approval
- Real-time monitoring dashboard
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from zentex.supervision.service import (
    AISupervisor,
    TaskSupervisor,
    SupervisedTaskManager,
    create_supervised_task_manager,
    get_ai_supervisor,
    get_task_supervisor,
    SupervisionLevel,
    ExecutionRecord,
    SupervisionAlert,
    initialize_supervision,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/supervision", tags=["AI Supervision"])


# Request/Response Models

class SupervisionStatusResponse(BaseModel):
    level: str
    total_executions: int
    running: int
    completed: int
    failed: int
    interventions_required: int
    active_alerts: int


class AlertResponse(BaseModel):
    alert_id: str
    timestamp: str
    severity: str
    category: str
    message: str
    execution_record_id: Optional[str] = None
    task_id: Optional[str] = None
    recommended_action: str
    acknowledged: bool
    resolved: bool


class ExecutionRecordResponse(BaseModel):
    record_id: str
    task_id: Optional[str] = None
    action_type: str
    start_time: str
    end_time: Optional[str] = None
    status: str
    verification_results: Dict[str, str]
    intervention_required: bool
    human_approved: bool
    supervisor_notes: List[str] = []


class InterventionRequest(BaseModel):
    task_id: str = Field(..., description="Task ID to intervene on")
    action: str = Field(..., description="Intervention action: approve, reject, pause, resume")
    reason: str = Field(..., description="Reason for intervention")
    operator_id: str = Field(default="human_supervisor", description="Operator ID")


class RuleUpdateRequest(BaseModel):
    rule_id: str
    enabled: bool = True


class DashboardResponse(BaseModel):
    supervision_summary: Dict[str, Any]
    active_alerts: List[AlertResponse]
    task_statistics: Dict[str, Any]
    timestamp: str


# Dependency injection

def get_supervised_task_manager() -> SupervisedTaskManager:
    """Get the supervised task manager instance."""
    raise HTTPException(
        status_code=500,
        detail="SupervisedTaskManager not properly configured. Use runtime integration."
    )


# Routes

@router.get("/status", response_model=SupervisionStatusResponse)
async def get_supervision_status(
    supervisor: AISupervisor = Depends(get_ai_supervisor)
):
    """Get current supervision system status."""
    summary = supervisor.get_execution_summary()
    
    return SupervisionStatusResponse(
        level=summary["supervision_level"],
        total_executions=summary["total_executions"],
        running=summary["running"],
        completed=summary["completed"],
        failed=summary["failed"],
        interventions_required=summary["interventions_required"],
        active_alerts=summary["active_alerts"]
    )


@router.get("/alerts", response_model=List[AlertResponse])
async def get_active_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    supervisor: AISupervisor = Depends(get_ai_supervisor)
):
    """Get active supervision alerts."""
    alerts = supervisor.get_active_alerts(severity_filter=severity)
    
    return [
        AlertResponse(
            alert_id=alert.alert_id,
            timestamp=alert.timestamp.isoformat(),
            severity=alert.severity,
            category=alert.category,
            message=alert.message,
            execution_record_id=alert.execution_record_id,
            task_id=alert.task_id,
            recommended_action=alert.recommended_action,
            acknowledged=alert.acknowledged,
            resolved=alert.resolved
        )
        for alert in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    supervisor: AISupervisor = Depends(get_ai_supervisor)
):
    """Acknowledge a supervision alert."""
    try:
        supervisor.acknowledge_alert(alert_id)
        return {"message": f"Alert {alert_id} acknowledged", "success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/executions", response_model=List[ExecutionRecordResponse])
async def get_execution_records(
    task_id: Optional[str] = Query(None, description="Filter by task ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum records to return"),
    supervisor: AISupervisor = Depends(get_ai_supervisor)
):
    """Get execution records with optional filtering."""
    records = list(supervisor.execution_records.values())
    
    # Apply filters
    if task_id:
        records = [r for r in records if r.task_id == task_id]
    if status:
        records = [r for r in records if r.status == status]
    
    # Sort by start time (most recent first) and limit
    records.sort(key=lambda r: r.start_time, reverse=True)
    records = records[:limit]
    
    return [
        ExecutionRecordResponse(
            record_id=record.record_id,
            task_id=record.task_id,
            action_type=record.action_type,
            start_time=record.start_time.isoformat(),
            end_time=record.end_time.isoformat() if record.end_time else None,
            status=record.status,
            verification_results={
                k: v.value for k, v in record.verification_results.items()
            },
            intervention_required=record.intervention_required,
            human_approved=record.human_approved,
            supervisor_notes=record.supervisor_notes
        )
        for record in records
    ]


@router.get("/executions/{record_id}", response_model=ExecutionRecordResponse)
async def get_execution_record(
    record_id: str,
    supervisor: AISupervisor = Depends(get_ai_supervisor)
):
    """Get details of a specific execution record."""
    record = supervisor.execution_records.get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Execution record {record_id} not found")
    
    return ExecutionRecordResponse(
        record_id=record.record_id,
        task_id=record.task_id,
        action_type=record.action_type,
        start_time=record.start_time.isoformat(),
        end_time=record.end_time.isoformat() if record.end_time else None,
        status=record.status,
        verification_results={
            k: v.value for k, v in record.verification_results.items()
        },
        intervention_required=record.intervention_required,
        human_approved=record.human_approved,
        supervisor_notes=record.supervisor_notes
    )


@router.post("/intervention", response_model=Dict[str, Any])
async def create_intervention(
    request: InterventionRequest,
    supervisor: AISupervisor = Depends(get_ai_supervisor),
    task_supervisor: TaskSupervisor = Depends(get_task_supervisor)
):
    """Create a human intervention for a task."""
    # Get the supervision record for this task
    supervision_record = task_supervisor.get_task_supervision_status(request.task_id)
    if not supervision_record:
        raise HTTPException(
            status_code=404,
            detail=f"No supervision record found for task {request.task_id}"
        )
    
    # Handle different intervention types
    try:
        if request.action == "approve":
            supervisor.require_human_approval(
                supervision_record.record_id,
                True,
                request.operator_id
            )
        elif request.action == "reject":
            supervisor.require_human_approval(
                supervision_record.record_id,
                False,
                request.operator_id
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid intervention action: {request.action}. Use 'approve' or 'reject'."
            )
        
        return {
            "success": True,
            "message": f"Intervention '{request.action}' applied to task {request.task_id}",
            "record_id": supervision_record.record_id,
            "operator_id": request.operator_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules", response_model=List[Dict[str, Any]])
async def get_supervision_rules(
    supervisor: AISupervisor = Depends(get_ai_supervisor)
):
    """Get all supervision rules."""
    return [
        {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "severity": rule.severity,
            "auto_intervene": rule.auto_intervene,
            "enabled": rule.enabled
        }
        for rule in supervisor.rules.values()
    ]


@router.post("/rules/update")
async def update_rule(
    request: RuleUpdateRequest,
    supervisor: AISupervisor = Depends(get_ai_supervisor)
):
    """Enable or disable a supervision rule."""
    if request.rule_id not in supervisor.rules:
        raise HTTPException(
            status_code=404,
            detail=f"Rule {request.rule_id} not found"
        )
    
    supervisor.rules[request.rule_id].enabled = request.enabled
    
    return {
        "success": True,
        "message": f"Rule {request.rule_id} {'enabled' if request.enabled else 'disabled'}"
    }


@router.get("/dashboard", response_model=DashboardResponse)
async def get_supervision_dashboard():
    """Get comprehensive supervision dashboard data."""
    # This would integrate with the SupervisedTaskManager in production
    # For now, return basic data from the supervisor
    supervisor = get_ai_supervisor()
    
    summary = supervisor.get_execution_summary()
    alerts = supervisor.get_active_alerts()
    
    return DashboardResponse(
        supervision_summary=summary,
        active_alerts=[
            AlertResponse(
                alert_id=alert.alert_id,
                timestamp=alert.timestamp.isoformat(),
                severity=alert.severity,
                category=alert.category,
                message=alert.message,
                execution_record_id=alert.execution_record_id,
                task_id=alert.task_id,
                recommended_action=alert.recommended_action,
                acknowledged=alert.acknowledged,
                resolved=alert.resolved
            )
            for alert in alerts[:10]
        ],
        task_statistics={},  # Would come from TaskManagementService
        timestamp=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    )


@router.post("/configure/level")
async def configure_supervision_level(
    level: str = Query(..., description="Supervision level: minimal, standard, strict, critical")
):
    """Configure the global supervision level."""
    try:
        supervision_level = SupervisionLevel(level)
        initialize_supervision(supervision_level)
        
        return {
            "success": True,
            "message": f"Supervision level set to {level}",
            "level": level
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid supervision level: {level}. Valid values: {[l.value for l in SupervisionLevel]}"
        )
