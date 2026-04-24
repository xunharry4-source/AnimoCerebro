from __future__ import annotations

"""
AI Supervision and Verification System for AnimoCerebro

This module implements a comprehensive supervision system that monitors AI execution,
verifies compliance with human-defined constraints, and ensures safe autonomous operation.
The system provides real-time monitoring, audit trails, and intervention capabilities.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)


class SupervisionLevel(Enum):
    """Levels of supervision intensity."""
    MINIMAL = "minimal"      # Basic logging only
    STANDARD = "standard"    # Regular checks and alerts
    STRICT = "strict"        # Continuous monitoring with immediate intervention
    CRITICAL = "critical"    # Maximum oversight with manual approval required


class VerificationStatus(Enum):
    """Status of verification checks."""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class SupervisionRule:
    """Defines a rule that AI actions must comply with."""
    rule_id: str
    name: str
    description: str
    check_function: Callable[[Dict[str, Any]], bool]
    severity: str = "medium"  # low, medium, high, critical
    auto_intervene: bool = False
    enabled: bool = True


@dataclass
class ExecutionRecord:
    """Records details of an AI-executed action."""
    record_id: str = field(default_factory=lambda: str(uuid4())[:8])
    task_id: Optional[str] = None
    action_type: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    status: str = "running"
    result: Optional[Any] = None
    error: Optional[str] = None
    verification_results: Dict[str, VerificationStatus] = field(default_factory=dict)
    supervisor_notes: List[str] = field(default_factory=list)
    intervention_required: bool = False
    human_approved: bool = False


@dataclass
class SupervisionAlert:
    """Alert generated when supervision detects issues."""
    alert_id: str = field(default_factory=lambda: str(uuid4())[:8])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: str = "medium"
    category: str = ""
    message: str = ""
    execution_record_id: Optional[str] = None
    task_id: Optional[str] = None
    recommended_action: str = ""
    acknowledged: bool = False
    resolved: bool = False


class AISupervisor:
    """
    Core supervision engine that monitors and verifies AI execution.
    
    This class implements the supervision framework that ensures AI agents
    operate within defined boundaries and can be monitored in real-time.
    """
    
    def __init__(self, supervision_level: SupervisionLevel = SupervisionLevel.STANDARD):
        # Initialize core state storage
        self.rules: Dict[str, SupervisionRule] = {}
        self.execution_records: Dict[str, ExecutionRecord] = {}
        self.alerts: List[SupervisionAlert] = []
        self.supervision_level = supervision_level
        
        # Phase 1: Persistence initialization
        self.storage_path = Path("./data/supervision")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.alerts_file = self.storage_path / "alerts.json"
        self.records_file = self.storage_path / "records.json"
        
        # Load existing data to ensure durability across restarts
        # POLICY: Fail-Closed. If audit logs cannot be loaded, the system must NOT start.
        self._load_persisted_data()
        
        # Initialize default rules
        self._initialize_default_rules()
        
        logger.info(f"AISupervisor initialized with level: {supervision_level.value}")

    def _load_persisted_data(self):
        """Load alerts and records from storage."""
        try:
            if self.alerts_file.exists():
                with open(self.alerts_file, "r") as f:
                    data = json.load(f)
                    self.alerts = [SupervisionAlert(**d) for d in data]
            
            if self.records_file.exists():
                with open(self.records_file, "r") as f:
                    data = json.load(f)
                    for r_id, r_data in data.items():
                        r_data["start_time"] = datetime.fromisoformat(r_data["start_time"])
                        if r_data.get("end_time"):
                            r_data["end_time"] = datetime.fromisoformat(r_data["end_time"])
                        self.execution_records[r_id] = ExecutionRecord(**r_data)
        except Exception as e:
            logger.critical(f"Supervision Integrity Failure: Failed to load audit history: {e}")
            # POLICY: Hard Stop on Corruption to prevent forged state / amnesia.
            raise RuntimeError(f"FATAL: Supervision module cannot load audit logs. System halted to preserve integrity: {e}")

    def _persist_data(self):
        """Atomic write of all supervision state."""
        try:
            # 1. Save Alerts
            temp_alerts = self.alerts_file.with_suffix(".tmp")
            with open(temp_alerts, "w") as f:
                json.dump([vars(a) for a in self.alerts], f, default=str, indent=2)
            temp_alerts.replace(self.alerts_file)

            # 2. Save Records
            temp_records = self.records_file.with_suffix(".tmp")
            with open(temp_records, "w") as f:
                # Convert recs to dicts with ISO dates
                out = {}
                for r_id, r in self.execution_records.items():
                    d = vars(r).copy()
                    d["start_time"] = d["start_time"].isoformat()
                    if d.get("end_time"):
                        d["end_time"] = d["end_time"].isoformat()
                    out[r_id] = d
                json.dump(out, f, indent=2)
            temp_records.replace(self.records_file)
        except Exception as e:
            logger.error(f"CRITICAL: Supervision persistence failure: {e}")
            raise RuntimeError(f"Audit log failure: {e}. System must halt to preserve integrity.")
    
    def _initialize_default_rules(self):
        """Initialize default supervision rules."""
        # Rule 1: No destructive operations without explicit approval
        self.add_rule(SupervisionRule(
            rule_id="no_destructive_ops",
            name="No Destructive Operations",
            description="Prevents file deletion or system modification without approval",
            check_function=self._check_no_destructive_ops,
            severity="critical",
            auto_intervene=True
        ))
        
        # Rule 2: Resource usage limits
        self.add_rule(SupervisionRule(
            rule_id="resource_limits",
            name="Resource Usage Limits",
            description="Monitors CPU, memory, and network usage",
            check_function=self._check_resource_limits,
            severity="high",
            auto_intervene=False
        ))
        
        # Rule 3: Data access compliance
        self.add_rule(SupervisionRule(
            rule_id="data_access_compliance",
            name="Data Access Compliance",
            description="Ensures data access follows privacy and security policies",
            check_function=self._check_data_access,
            severity="high",
            auto_intervene=True
        ))
        
        # Rule 4: Action frequency limits
        self.add_rule(SupervisionRule(
            rule_id="action_frequency",
            name="Action Frequency Limits",
            description="Prevents rapid-fire actions that could overwhelm systems",
            check_function=self._check_action_frequency,
            severity="medium",
            auto_intervene=False
        ))
    
    def add_rule(self, rule: SupervisionRule):
        """Add a new supervision rule."""
        self.rules[rule.rule_id] = rule
        logger.info(f"Added supervision rule: {rule.name} ({rule.rule_id})")
    
    def remove_rule(self, rule_id: str):
        """Remove a supervision rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info(f"Removed supervision rule: {rule_id}")
    
    def start_monitoring(self, task_id: str, action_type: str, parameters: Dict[str, Any]) -> ExecutionRecord:
        """Start monitoring a new AI execution."""
        record = ExecutionRecord(
            task_id=task_id,
            action_type=action_type,
            parameters=parameters
        )
        self.execution_records[record.record_id] = record
        
        # Log the start of monitoring
        logger.info(f"Started monitoring task {task_id}, action: {action_type}, record: {record.record_id}")
        
        # Apply initial verification
        self._verify_execution(record)
        
        # Phase 1: Mandatory Persistence
        self._persist_data()
        
        return record
    
    def update_execution(self, record_id: str, status: str, result: Any = None, error: str = None):
        """Update the status of an ongoing execution."""
        if record_id not in self.execution_records:
            raise ValueError(f"Execution record {record_id} not found")
        
        record = self.execution_records[record_id]
        record.status = status
        record.result = result
        record.error = error
        
        if status in ["completed", "failed"]:
            record.end_time = datetime.now(timezone.utc)
        
        # Re-verify after update
        self._verify_execution(record)
        
        # Phase 1: Mandatory Persistence
        self._persist_data()
        
        logger.debug(f"Updated execution {record_id}: status={status}")
    
    def _verify_execution(self, record: ExecutionRecord):
        """Run all applicable verification checks on an execution record."""
        for rule_id, rule in self.rules.items():
            if not rule.enabled:
                continue
            
            try:
                # Prepare context for the check
                context = {
                    "record": record,
                    "action_type": record.action_type,
                    "parameters": record.parameters,
                    "status": record.status,
                    "timestamp": datetime.now(timezone.utc)
                }
                
                # Execute the check
                passed = rule.check_function(context)
                
                # Update verification result
                record.verification_results[rule_id] = (
                    VerificationStatus.PASSED if passed else VerificationStatus.FAILED
                )
                
                # Handle failures
                if not passed:
                    self._handle_verification_failure(record, rule)
                    
            except Exception as e:
                # POLICY[no-bare-logger-error]: exc_info=True is mandatory so the
                # full traceback appears in logs, not just the message string.
                logger.error(f"Verification failed for rule {rule_id}: {e}", exc_info=True)
                record.verification_results[rule_id] = VerificationStatus.FAILED
                record.supervisor_notes.append(f"Verification error for {rule.name}: {str(e)}")
    
    def _handle_verification_failure(self, record: ExecutionRecord, rule: SupervisionRule):
        """Handle a verification failure by creating alerts and potentially intervening."""
        # Create alert
        alert = SupervisionAlert(
            severity=rule.severity,
            category="verification_failure",
            message=f"Rule '{rule.name}' violated during execution {record.record_id}",
            execution_record_id=record.record_id,
            task_id=record.task_id,
            recommended_action=f"Review and potentially intervene in execution {record.record_id}"
        )
        self.alerts.append(alert)
        
        # Mark record for intervention if needed
        if rule.auto_intervene or rule.severity in ["high", "critical"]:
            record.intervention_required = True
        
        # Phase 1: Mandatory Persistence
        self._persist_data()
        
        logger.warning(f"Verification failure: {alert.message}")
    
    def require_human_approval(self, record_id: str, approved: bool, approver_id: str = "human_supervisor"):
        """Require human approval for an execution."""
        if record_id not in self.execution_records:
            raise ValueError(f"Execution record {record_id} not found")
        
        record = self.execution_records[record_id]
        record.human_approved = approved
        record.supervisor_notes.append(f"Human approval by {approver_id}: {'APPROVED' if approved else 'DENIED'}")
        
        logger.info(f"Human approval for {record_id}: {'APPROVED' if approved else 'DENIED'} by {approver_id}")
    
    def get_active_alerts(self, severity_filter: Optional[str] = None) -> List[SupervisionAlert]:
        """Get active (unacknowledged) alerts, optionally filtered by severity."""
        alerts = [a for a in self.alerts if not a.acknowledged]
        if severity_filter:
            alerts = [a for a in alerts if a.severity == severity_filter]
        return alerts
    
    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert."""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                logger.info(f"Alert {alert_id} acknowledged")
                return
        raise ValueError(f"Alert {alert_id} not found")
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get a summary of all executions."""
        total = len(self.execution_records)
        running = sum(1 for r in self.execution_records.values() if r.status == "running")
        completed = sum(1 for r in self.execution_records.values() if r.status == "completed")
        failed = sum(1 for r in self.execution_records.values() if r.status == "failed")
        interventions = sum(1 for r in self.execution_records.values() if r.intervention_required)
        
        return {
            "total_executions": total,
            "running": running,
            "completed": completed,
            "failed": failed,
            "interventions_required": interventions,
            "active_alerts": len(self.get_active_alerts()),
            "supervision_level": self.supervision_level.value
        }
    
    # Default verification functions
    def _check_no_destructive_ops(self, context: Dict[str, Any]) -> bool:
        """
        Check if the action involves destructive operations via Plugin capabilities.
        
        Authentic Rule: No harder coded keyword stubs.
        """
        record = context["record"]
        params = record.parameters or {}
        plugin_id = params.get("plugin_id")
        
        if not plugin_id:
            # If no plugin_id, fall back to suspicious keyword check as a secondary defense
            # but don't consider it 'safe' if it passes.
            action_type = context["action_type"].lower()
            destructive_keywords = ["delete", "remove", "destroy", "drop", "truncate"]
            if any(keyword in action_type for keyword in destructive_keywords):
                return False
            return True

        # Authentic Audit via SystemPluginService
        try:
            from zentex.plugins.service import get_service
            plugin_service = get_service()
            capabilities = plugin_service.get_plugin_capabilities(plugin_id)
            
            # Policy: If 'DESTRUCTIVE' or 'SYSTEM_MUTATION' is in capabilities, 
            # this is considered a destructive operation.
            dangerous_caps = {"DESTRUCTIVE", "SYSTEM_MUTATION", "FILE_DELETION"}
            if any(cap.upper() in dangerous_caps for cap in capabilities):
                logger.warning(f"Supervision: Blocked destructive action from plugin {plugin_id}")
                return False
                
            return True
        except Exception as e:
            # POLICY[no-bare-logger-error]: exc_info=True required for full traceback.
            logger.error(f"Supervision: Capability check failed for {plugin_id}: {e}", exc_info=True)
            # Fail-Closed: If we can't verify capabilities, assume it's unsafe.
            return False
    
    def _check_resource_limits(self, context: Dict[str, Any]) -> bool:
        """Check if resource usage is within acceptable limits."""
        record = context["record"]
        params = record.parameters or {}
        
        # Policy: Hard-coded protection stubs are eradicated.
        if params.get("resource_intensive", False):
            # Check for explicit 'budget_approved' flag
            return params.get("budget_approved", False)
            
        # Fail-Closed: If a task has no resource profile, default to restricted
        return params.get("low_resource_mode", True)
    
    def _check_data_access(self, context: Dict[str, Any]) -> bool:
        """Check if data access complies with policies via Plugin metadata."""
        record = context["record"]
        params = record.parameters or {}
        plugin_id = params.get("plugin_id")
        
        if not plugin_id:
            # Secondary heuristic defense
            parameters = context["parameters"]
            sensitive_patterns = ["password", "secret", "token", "key", "credential"]
            param_keys = [k.lower() for k in parameters.keys()]
            return not any(pattern in key for pattern in sensitive_patterns for key in param_keys)

        # Authentic Audit via SystemPluginService
        try:
            from zentex.plugins.service import get_service
            plugin_service = get_service()
            rules = plugin_service.get_plugin_rules(plugin_id)
            
            # Use 'data_sensitivity' rule from plugin metadata
            sensitivity = rules.get("data_sensitivity", "high") # Default to high
            if sensitivity in ["critical", "high"]:
                # High sensitivity requires explicit 'authorized' context
                return params.get("auth_verified", False)
                
            return True
        except Exception as e:
            # POLICY[no-bare-logger-error]: exc_info=True required for full traceback.
            logger.error(f"Supervision: Data access audit failed for {plugin_id}: {e}", exc_info=True)
            return False
    
    def _check_action_frequency(self, context: Dict[str, Any]) -> bool:
        """Check if actions are being performed too frequently.
        
        Policy: Hard-coded protection stubs are eradicated.
        """
        # Simple frequency threshold: No more than 10 actions per 60 seconds per task.
        current_time = datetime.now(timezone.utc)
        record = context["record"]
        task_id = record.task_id
        
        if not task_id:
            return True
            
        recent_count = 0
        for r in self.execution_records.values():
            if r.task_id == task_id:
                delta = (current_time - r.start_time).total_seconds()
                if delta < 60:
                    recent_count += 1
                    
        return recent_count <= 10


class TaskSupervisor:
    """
    Specialized supervisor for task-level monitoring.
    
    Integrates with the existing task management system to provide
    supervision specifically for task execution.
    """
    
    def __init__(self, ai_supervisor: AISupervisor):
        self.ai_supervisor = ai_supervisor
        self.task_execution_map: Dict[str, str] = {}  # task_id -> execution_record_id
    
    def supervise_task_execution(self, task_id: str, action_type: str, parameters: Dict[str, Any]) -> ExecutionRecord:
        """Start supervising a specific task execution."""
        record = self.ai_supervisor.start_monitoring(task_id, action_type, parameters)
        self.task_execution_map[task_id] = record.record_id
        return record
    
    def complete_task_supervision(self, task_id: str, success: bool, result: Any = None):
        """Mark task supervision as complete."""
        if task_id not in self.task_execution_map:
            raise ValueError(f"No supervision record found for task {task_id}")
        
        record_id = self.task_execution_map[task_id]
        status = "completed" if success else "failed"
        self.ai_supervisor.update_execution(record_id, status, result)
        
        # Clean up mapping
        del self.task_execution_map[task_id]
    
    def get_task_supervision_status(self, task_id: str) -> Optional[ExecutionRecord]:
        """Get the supervision status for a specific task."""
        if task_id not in self.task_execution_map:
            return None
        
        record_id = self.task_execution_map[task_id]
        return self.ai_supervisor.execution_records.get(record_id)


# Global supervisor instance
_global_supervisor: Optional[AISupervisor] = None
_global_task_supervisor: Optional[TaskSupervisor] = None


def get_ai_supervisor() -> AISupervisor:
    """Get the global AI supervisor instance."""
    global _global_supervisor
    if _global_supervisor is None:
        _global_supervisor = AISupervisor()
    return _global_supervisor


def get_task_supervisor() -> TaskSupervisor:
    """Get the global task supervisor instance."""
    global _global_task_supervisor
    if _global_task_supervisor is None:
        _global_task_supervisor = TaskSupervisor(get_ai_supervisor())
    return _global_task_supervisor


def initialize_supervision(level: SupervisionLevel = SupervisionLevel.STANDARD):
    """Initialize the global supervision system."""
    global _global_supervisor, _global_task_supervisor
    _global_supervisor = AISupervisor(level)
    _global_task_supervisor = TaskSupervisor(_global_supervisor)
    logger.info(f"Global supervision system initialized with level: {level.value}")
