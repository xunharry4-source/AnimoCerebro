from __future__ import annotations

"""
Integration module connecting AI supervision with existing task management.

This module bridges the new AI supervision system with the existing
TaskManagementService to ensure all task executions are properly supervised.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from zentex.tasks.service import TaskManagementService
from zentex.tasks.service import ZentexTask, TaskStatus
from zentex.supervision.ai_supervisor import (
    AISupervisor, 
    TaskSupervisor, 
    get_ai_supervisor, 
    get_task_supervisor,
    ExecutionRecord,
    SupervisionLevel
)

logger = logging.getLogger(__name__)


class SupervisedTaskManager:
    """
    Wrapper around TaskManagementService that adds AI supervision.
    
    This class ensures that all task operations are monitored and verified
    by the AI supervision system before execution.
    """
    
    def __init__(
        self,
        task_service: TaskManagementService,
        ai_supervisor: Optional[AISupervisor] = None,
        task_supervisor: Optional[TaskSupervisor] = None
    ):
        self.task_service = task_service
        self.ai_supervisor = ai_supervisor or get_ai_supervisor()
        self.task_supervisor = task_supervisor or get_task_supervisor()
        
        logger.info("SupervisedTaskManager initialized")
    
    async def create_and_supervise_task(self, payload: Dict[str, Any]) -> ZentexTask:
        """
        Create a new task and immediately start supervising it.
        
        Args:
            payload: Task creation payload
            
        Returns:
            Created ZentexTask instance
        """
        # First create the task using the underlying service
        task = await self.task_service.create_task(payload)
        
        # Start supervision for this task
        try:
            supervision_params = {
                "task_type": task.task_type.value,
                "priority": task.priority.value,
                "title": task.title,
                "created_at": task.created_at.isoformat()
            }
            
            self.task_supervisor.supervise_task_execution(
                task_id=task.task_id,
                action_type=f"task_creation:{task.task_type.value}",
                parameters=supervision_params
            )
            
            logger.info(f"Task {task.task_id} created and under supervision")
            
        except Exception as e:
            logger.error(f"Failed to start supervision for task {task.task_id}: {e}")
            # Don't fail task creation if supervision fails, but log it
            task.remarks = f"{task.remarks or ''} [Supervision initialization failed: {str(e)}]"
        
        return task
    
    async def execute_task_with_supervision(
        self,
        task_id: str,
        execution_function: callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a task function under supervision.
        
        Args:
            task_id: ID of the task to execute
            execution_function: Function to execute for this task
            *args: Arguments to pass to the execution function
            **kwargs: Keyword arguments to pass to the execution function
            
        Returns:
            Result of the execution function
        """
        # Get the task
        task = self.task_service.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Check if task is already under supervision
        supervision_record = self.task_supervisor.get_task_supervision_status(task_id)
        if not supervision_record:
            # Start supervision if not already started
            supervision_record = self.task_supervisor.supervise_task_execution(
                task_id=task_id,
                action_type=f"task_execution:{task.task_type.value}",
                parameters={
                    "title": task.title,
                    "priority": task.priority.value,
                    "started_at": datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Check if human approval is required
        if supervision_record.intervention_required and not supervision_record.human_approved:
            raise PermissionError(
                f"Task {task_id} requires human approval before execution. "
                f"Please review supervision alerts and approve if appropriate."
            )
        
        try:
            # Update task status to in_progress
            self.task_service.update_task_status(task_id, TaskStatus.IN_PROGRESS)
            
            # Execute the function
            result = execution_function(*args, **kwargs)
            
            # Mark execution as successful
            self.task_supervisor.complete_task_supervision(task_id, True, result)
            
            # Update task status to done
            self.task_service.update_task_status(
                task_id, 
                TaskStatus.DONE, 
                remarks="Execution completed successfully under supervision"
            )
            
            logger.info(f"Task {task_id} executed successfully under supervision")
            return result
            
        except Exception as e:
            # Mark execution as failed
            self.task_supervisor.complete_task_supervision(task_id, False, str(e))
            
            # Update task status to failed
            self.task_service.update_task_status(
                task_id, 
                TaskStatus.FAILED, 
                remarks=f"Execution failed: {str(e)}"
            )
            
            logger.error(f"Task {task_id} execution failed: {e}")
            raise
    
    def intervene_on_task(self, task_id: str, action: str, reason: str, operator_id: str = "human_supervisor") -> Dict[str, Any]:
        """
        Intervene in a task's execution.
        
        Args:
            task_id: ID of the task to intervene on
            action: Intervention action (pause, resume, approve, reject, etc.)
            reason: Reason for intervention
            operator_id: ID of the operator performing the intervention
            
        Returns:
            Intervention result
        """
        # Get supervision record
        supervision_record = self.task_supervisor.get_task_supervision_status(task_id)
        if not supervision_record:
            raise ValueError(f"No supervision record found for task {task_id}")
        
        # Handle different intervention types
        if action == "approve":
            self.ai_supervisor.require_human_approval(supervision_record.record_id, True, operator_id)
        elif action == "reject":
            self.ai_supervisor.require_human_approval(supervision_record.record_id, False, operator_id)
        elif action == "pause":
            self.task_service.update_task_status(task_id, TaskStatus.BLOCKED, remarks=f"Paused by {operator_id}: {reason}")
        elif action == "resume":
            self.task_service.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks=f"Resumed by {operator_id}: {reason}")
        
        # Also use the original task service intervention method
        from uuid import uuid4
        idempotency_key = f"intervention-{task_id}-{uuid4().hex[:8]}"
        result = self.task_service.intervene(
            task_id=task_id,
            action=action,
            idempotency_key=idempotency_key,
            remarks=reason,
            operator_id=operator_id
        )
        
        logger.info(f"Intervention on task {task_id}: {action} by {operator_id}")
        return result
    
    def get_supervision_dashboard(self) -> Dict[str, Any]:
        """
        Get a comprehensive supervision dashboard view.
        
        Returns:
            Dashboard data including supervision stats, active alerts, etc.
        """
        # Get execution summary from AI supervisor
        execution_summary = self.ai_supervisor.get_execution_summary()
        
        # Get active alerts
        active_alerts = self.ai_supervisor.get_active_alerts()
        
        # Get task statistics from underlying service
        task_stats = self.task_service.get_task_statistics()
        
        # Combine into dashboard
        dashboard = {
            "supervision_summary": execution_summary,
            "active_alerts": [
                {
                    "alert_id": alert.alert_id,
                    "severity": alert.severity,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "task_id": alert.task_id
                }
                for alert in active_alerts[:10]  # Limit to 10 most recent
            ],
            "task_statistics": task_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return dashboard
    
    def acknowledge_alert(self, alert_id: str):
        """Acknowledge a supervision alert."""
        self.ai_supervisor.acknowledge_alert(alert_id)
        logger.info(f"Alert {alert_id} acknowledged")


def create_supervised_task_manager(
    task_service: TaskManagementService,
    supervision_level: SupervisionLevel = SupervisionLevel.STANDARD
) -> SupervisedTaskManager:
    """
    Factory function to create a SupervisedTaskManager with proper initialization.
    
    Args:
        task_service: Existing TaskManagementService instance
        supervision_level: Level of supervision to apply
        
    Returns:
        Configured SupervisedTaskManager instance
    """
    # Initialize supervision system
    from zentex.supervision.ai_supervisor import initialize_supervision
    initialize_supervision(supervision_level)
    
    # Create and return the supervised manager
    return SupervisedTaskManager(task_service)
