from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    WAITING_CONFIRMATION = "waiting_confirmation"
    SUSPENDED = "suspended"
    DONE = "done"
    FAILED = "failed"
    ARCHIVED = "archived"

class TaskType(str, Enum):
    COGNITIVE_STEP = "cognitive_step"
    AGENT_DELEGATION = "agent_delegation"
    SYSTEM_ACTION = "system_action"
    INTERVENTION = "intervention"
    MISSION = "mission" # High-level parent task

class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class CoordinationMode(str, Enum):
    PARALLEL = "parallel" # Can be done independently
    BUNDLE = "bundle" # Must be done together (atomic)
    SEQUENTIAL = "sequential" # One after another

class SuspendedTask(BaseModel):
    """Represents a suspended task with recovery context"""
    task_id: str
    original_status: TaskStatus
    suspension_reason: str
    recovery_conditions: List[str] = Field(default_factory=list)
    suspension_context: Dict[str, Any] = Field(default_factory=dict)
    suspended_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    auto_resume_at: Optional[datetime] = None

class TaskContract(BaseModel):
    retriable: bool = True
    retry_budget: int = 3
    serial_only: bool = False
    allow_parallel: bool = True
    require_leader: bool = False
    degradable: bool = False
    coordination_mode: CoordinationMode = CoordinationMode.PARALLEL
    failure_strategy: str = "halt" # halt, skip, retry_all, ignore
    recovery_action: Optional[str] = None

class ZentexTask(BaseModel):
    task_id: str
    parent_task_id: Optional[str] = None # For decomposition hierarchy
    subtask_ids: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list) # List of task_ids
    bundle_id: Optional[str] = None # For bundle coordination
    subtask_id: Optional[str] = None
    idempotency_key: str
    title: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    progress: float = 0.0 # 0.0 to 1.0
    originator_id: str
    target_id: Optional[str] = None # e.g. agent_id if delegation
    remarks: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    estimated_duration: Optional[int] = None # in minutes
    tags: List[str] = Field(default_factory=list)
    contract: TaskContract = Field(default_factory=TaskContract)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def update_status(self, new_status: TaskStatus, remarks: Optional[str] = None):
        if new_status == TaskStatus.IN_PROGRESS and not self.started_at:
            self.started_at = datetime.now(timezone.utc)
        if new_status in [TaskStatus.DONE, TaskStatus.FAILED]:
            self.completed_at = datetime.now(timezone.utc)
            self.progress = 1.0 if new_status == TaskStatus.DONE else self.progress
        
        self.status = new_status
        if remarks:
            self.remarks = remarks
        self.last_updated_at = datetime.now(timezone.utc)

    def get_priority_score(self) -> int:
        """Convert priority to numeric score for sorting"""
        priority_scores = {
            TaskPriority.CRITICAL: 4,
            TaskPriority.HIGH: 3,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 1
        }
        return priority_scores.get(self.priority, 2)

    def is_overdue(self) -> bool:
        """Check if task is overdue"""
        if not self.deadline:
            return False
        return datetime.now(timezone.utc) > self.deadline

    def can_be_resumed(self, recovery_conditions_met: bool = True) -> bool:
        """Check if suspended task can be resumed"""
        if self.status != TaskStatus.SUSPENDED:
            return False
        if not recovery_conditions_met:
            return False
        return True
