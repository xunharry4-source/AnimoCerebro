from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"

class TaskEnvelope(BaseModel):
    """ The authoritative container for task information sent to any Zentex pillar. """
    task_id: str
    title: str
    purpose: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    originator_id: str
    priority: TaskPriority = TaskPriority.MEDIUM
    trace_id: str
    deadline: Optional[str] = None # ISO format string

class TaskFeedback(BaseModel):
    """ The authoritative status report sent back from any Zentex pillar. """
    task_id: str
    status: TaskStatus
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    progress: float = 0.0 # 0.0 to 1.0
    remarks: Optional[str] = None
    completed_at: Optional[str] = None # ISO format string
