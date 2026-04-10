from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from zentex.supervision.ai_supervisor import (
    AISupervisor,
    TaskSupervisor,
    get_ai_supervisor,
    get_task_supervisor,
    SupervisionLevel,
    ExecutionRecord,
    SupervisionAlert,
    initialize_supervision
)
from zentex.supervision.integration import SupervisedTaskManager

logger = logging.getLogger(__name__)


class InterventionRequest(BaseModel):
    """Request model for human intervention."""
    task_id: str = Field(..., description="ID of the task to intervene on")
    action: str = Field(..., description="Action to perform: approve, reject, pause, resume")
    reason: str = Field(..., description="Reason for the intervention")
    operator_id: str = Field(default="human_supervisor", description="ID of the operator")


class RuleUpdateRequest(BaseModel):
    """Request model for updating a supervision rule."""
    rule_id: str = Field(..., description="ID of the rule to update")
    enabled: bool = Field(..., description="Whether the rule should be enabled")


class SupervisionService:
    """
    Unified service for AI Supervision and Verification.
    
    This service acts as the primary external interface (对外联系) for the supervision module,
    providing a clean API for the Web Console and other system components to monitor
    AI executions, handle alerts, and perform human interventions.
    """
    
    def __init__(
        self, 
        ai_supervisor: Optional[AISupervisor] = None,
        task_supervisor: Optional[TaskSupervisor] = None,
        supervised_manager: Optional[SupervisedTaskManager] = None
    ) -> None:
        """
        Initialize the SupervisionService.
        
        Args:
            ai_supervisor: The core AI supervisor instance. Defaults to global instance.
            task_supervisor: The task-level supervisor. Defaults to global instance.
            supervised_manager: Integrated task manager. Optional.
        """
        self.ai_supervisor = ai_supervisor or get_ai_supervisor()
        self.task_supervisor = task_supervisor or get_task_supervisor()
        self.supervised_manager = supervised_manager
        
        logger.info("SupervisionService initialized")
        
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get a summary of the current state of the supervision system.
        
        Returns:
            Dictionary containing execution statistics and supervision level.
        """
        return self.ai_supervisor.get_execution_summary()
    
    def list_active_alerts(self, severity: Optional[str] = None) -> List[SupervisionAlert]:
        """
        List all active (unacknowledged) supervision alerts.
        
        Args:
            severity: Optional filter for alert severity.
            
        Returns:
            List of active SupervisionAlert objects.
        """
        return self.ai_supervisor.get_active_alerts(severity_filter=severity)
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge a supervision alert.
        
        Args:
            alert_id: The unique ID of the alert.
            
        Returns:
            True if acknowledged, False if alert not found.
        """
        try:
            self.ai_supervisor.acknowledge_alert(alert_id)
            return True
        except ValueError:
            logger.warning(f"Failed to acknowledge non-existent alert: {alert_id}")
            return False
            
    def get_execution_records(
        self, 
        task_id: Optional[str] = None, 
        status: Optional[str] = None, 
        limit: int = 50
    ) -> List[ExecutionRecord]:
        """
        Retrieve execution records with optional filtering.
        
        Args:
            task_id: Filter by specific task ID.
            status: Filter by execution status (running, completed, failed).
            limit: Maximum number of records to return.
            
        Returns:
            List of ExecutionRecord objects sorted by start time (newest first).
        """
        records = list(self.ai_supervisor.execution_records.values())
        
        if task_id:
            records = [r for r in records if r.task_id == task_id]
        if status:
            records = [r for r in records if r.status == status]
        
        # Sort by start time descending
        records.sort(key=lambda r: r.start_time, reverse=True)
        return records[:limit]
        
    def perform_intervention(self, request: InterventionRequest) -> Dict[str, Any]:
        """
        Apply a human intervention to a task or execution.
        
        Args:
            request: The intervention request containing task_id and action.
            
        Returns:
            Result of the intervention.
        """
        # If we have a supervised manager, use its richer intervention logic
        if self.supervised_manager:
            return self.supervised_manager.intervene_on_task(
                task_id=request.task_id,
                action=request.action,
                reason=request.reason,
                operator_id=request.operator_id
            )
        
        # Fallback to basic supervision intervention
        record = self.task_supervisor.get_task_supervision_status(request.task_id)
        if not record:
            raise ValueError(f"No supervision record found for task {request.task_id}")
            
        if request.action in ["approve", "reject"]:
            approved = (request.action == "approve")
            self.ai_supervisor.require_human_approval(
                record.record_id, 
                approved=approved, 
                approver_id=request.operator_id
            )
            return {
                "success": True, 
                "message": f"Applied {request.action} to {request.task_id}",
                "record_id": record.record_id
            }
        else:
            raise NotImplementedError(
                f"Action '{request.action}' requires integration with SupervisedTaskManager"
            )

    def update_rule_status(self, rule_id: str, enabled: bool) -> bool:
        """
        Enable or disable a specific supervision rule.
        
        Args:
            rule_id: The unique ID of the rule.
            enabled: Boolean indicating if the rule should be active.
            
        Returns:
            True if updated, False if rule not found.
        """
        if rule_id in self.ai_supervisor.rules:
            self.ai_supervisor.rules[rule_id].enabled = enabled
            logger.info(f"Supervision rule '{rule_id}' set to enabled={enabled}")
            return True
        return False

    def get_all_rules(self) -> List[Dict[str, Any]]:
        """
        Get all defined supervision rules.
        
        Returns:
            List of rule definitions.
        """
        return [
            {
                "rule_id": rule.rule_id,
                "name": rule.name,
                "description": rule.description,
                "severity": rule.severity,
                "auto_intervene": rule.auto_intervene,
                "enabled": rule.enabled
            }
            for rule in self.ai_supervisor.rules.values()
        ]

    def configure_system(self, level: str) -> bool:
        """
        Configure the global supervision system level.
        
        Args:
            level: The supervision level (minimal, standard, strict, critical).
            
        Returns:
            True if configured successfully, False otherwise.
        """
        try:
            supervision_level = SupervisionLevel(level)
            initialize_supervision(supervision_level)
            # Re-fetch supervisors from global state after initialization
            self.ai_supervisor = get_ai_supervisor()
            self.task_supervisor = get_task_supervisor()
            return True
        except ValueError:
            logger.error(f"Invalid supervision level: {level}")
            return False

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data for the supervision system.
        
        Returns:
            Dictionary containing summary, active alerts, and timestamp.
        """
        if self.supervised_manager:
            return self.supervised_manager.get_supervision_dashboard()
        
        summary = self.get_system_status()
        active_alerts = self.list_active_alerts()
        
        return {
            "supervision_summary": summary,
            "active_alerts": [
                {
                    "alert_id": a.alert_id,
                    "severity": a.severity,
                    "message": a.message,
                    "timestamp": a.timestamp.isoformat(),
                    "task_id": a.task_id
                }
                for a in active_alerts[:10]
            ],
            "task_statistics": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
