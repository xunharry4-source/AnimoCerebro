from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Import verification models
try:
    from zentex.tasks.verification.models import VerificationConfig
except ImportError:
    # Fallback for circular import issues
    class VerificationConfig(BaseModel):
        enabled: bool = False

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
    
    # Verification configuration (embedded)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)

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

    # -----------------------------------------------------------------------
    # Execution result fields — written by TaskExecutionWorker after the
    # plugin finishes.  These fields are persisted to the DB via migrate_task_schema.
    # -----------------------------------------------------------------------
    # The plugin that was selected and actually ran this task
    dispatch_plugin_id: Optional[str] = None
    # Structured output returned by the plugin (None until execution completes)
    execution_output: Optional[Dict[str, Any]] = None
    # Wall-clock timestamps for the execution window
    execution_started_at: Optional[datetime] = None
    execution_finished_at: Optional[datetime] = None
    # Last error message (overwritten on every attempt)
    last_error: Optional[str] = None
    # How many execution attempts have been made
    attempt_count: int = 0

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


class DecompositionContext(BaseModel):
    """
    Unified context for mission decomposition across all decomposer plugins.
    This ensures consistent memory/experience injection into mock, LLM, and Semantic Kernel paths.
    
    Phase A1 standardization: All decomposers receive this structure.
    """
    mission_query: str = Field(description="Normalized query from mission title, remarks, and tags")
    
    # Memory-sourced insights
    similar_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Historical similar tasks")
    historical_success_rate: Optional[float] = Field(default=None, description="Success rate of similar tasks")
    common_tags: List[str] = Field(default_factory=list, description="High-frequency tags from similar tasks")
    risk_hints: List[str] = Field(default_factory=list, description="Risk warnings from historical analysis")
    preferred_executor_patterns: List[Dict[str, Any]] = Field(default_factory=list, description="Executor patterns from history")
    
    # Task metadata context
    task_type: Optional[str] = Field(default=None, description="Specific task type for decomposition tuning")
    priority: Optional[str] = Field(default=None, description="Task priority level")
    tags: List[str] = Field(default_factory=list, description="Task tags for context")
    
    # Decomposition hints
    estimated_scope: Optional[str] = Field(default=None, description="Estimated complexity: simple/medium/complex")
    execution_constraints: List[str] = Field(default_factory=list, description="Constraints on execution approach")
    
    @property
    def memory_text(self) -> str:
        """Generate a formatted text representation of memory context for prompt injection."""
        lines = []
        
        if self.similar_tasks:
            lines.append("历史相似任务经验:")
            for task in self.similar_tasks[:5]:
                status = task.get("status", "unknown")
                success = task.get("success")
                title = task.get("title", "N/A")
                lines.append(f"  - {title} | status={status} | success={success}")
        
        if self.risk_hints:
            lines.append("\n风险提示:")
            for hint in self.risk_hints:
                lines.append(f"  - {hint}")
        
        if self.common_tags:
            lines.append(f"\n高频标签: {', '.join(self.common_tags[:10])}")
        
        if self.historical_success_rate is not None:
            lines.append(f"\n相似任务成功率: {self.historical_success_rate:.1%}")
        
        return "\n".join(lines) if lines else ""


class FailureMode(str, Enum):
    """Explicit failure modes that a subtask may encounter."""
    TIMEOUT = "timeout"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    DEPENDENCY_VIOLATION = "dependency_violation"
    CAPABILITY_MISMATCH = "capability_mismatch"
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_ERROR = "execution_error"
    PARTIAL_COMPLETION = "partial_completion"
    RESOURCE_UNAVAILABLE = "resource_unavailable"


class SubtaskIntent(BaseModel):
    """
    Phase A2: Standardized schema for subtask decomposition output.
    Represents what a subtask is meant to accomplish and how it should be handled.
    """
    # Identity & semantic meaning
    local_id: str = Field(description="Unique identifier within decomposition (e.g. step-1, step-2)")
    title: str = Field(description="Human-readable subtask title")
    objective: str = Field(description="Clear statement of what the subtask must achieve")
    
    # Task structure
    task_type: TaskType = Field(description="Type of subtask: cognitive/delegation/system/intervention")
    content: str = Field(description="Detailed description of what should be done")
    requirements: List[str] = Field(default_factory=list, description="Concrete actions/checks required")
    
    # Execution constraints & coordination
    coordination_mode: CoordinationMode = Field(default=CoordinationMode.PARALLEL)
    depends_on: List[str] = Field(default_factory=list, description="Local IDs of tasks this depends on")
    
    # Expected outcomes & validation
    expected_output: Optional[str] = Field(default=None, description="What should result from successful completion")
    success_criteria: List[str] = Field(default_factory=list, description="Verifiable conditions for success")
    acceptable_failure_modes: List[FailureMode] = Field(
        default_factory=list,
        description="Failure modes that should trigger specific recovery actions"
    )
    
    # Execution controls
    maximum_attempts: int = Field(default=3, description="Maximum retry attempts before escalation")
    execution_timeout_seconds: Optional[int] = Field(default=None, description="Hard timeout in seconds")
    estimated_duration_seconds: Optional[int] = Field(default=None, description="Expected execution duration")
    
    # Failure handling policy
    on_failure_action: str = Field(
        default="retry",
        description="Default action on failure: retry, skip, fallback, escalate, or abort_parent"
    )
    fallback_subtask_ids: List[str] = Field(
        default_factory=list,
        description="Alternative subtask IDs to try if this one fails"
    )
    
    # Metadata for routing & prioritization
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    tags: List[str] = Field(default_factory=list, description="Categorical tags for routing/filtering")
    required_capabilities: List[str] = Field(default_factory=list, description="Capabilities executor must possess")
    
    def validate_intent(self) -> tuple[bool, Optional[str]]:
        """
        Validate that intent is well-formed and self-consistent.
        Returns (is_valid, error_message).
        """
        if not self.title or not self.title.strip():
            return False, "title cannot be empty"
        
        if not self.objective or not self.objective.strip():
            return False, "objective cannot be empty"
        
        if not self.content or not self.content.strip():
            return False, "content cannot be empty"
        
        if self.maximum_attempts < 1:
            return False, "maximum_attempts must be at least 1"
        
        if self.execution_timeout_seconds is not None and self.execution_timeout_seconds < 1:
            return False, "execution_timeout_seconds must be positive or None"
        
        if self.estimated_duration_seconds is not None and self.estimated_duration_seconds < 1:
            return False, "estimated_duration_seconds must be positive or None"
        
        valid_actions = {"retry", "skip", "fallback", "escalate", "abort_parent"}
        if self.on_failure_action not in valid_actions:
            return False, f"on_failure_action must be one of {valid_actions}"
        
        # Validate consistency
        if self.on_failure_action == "fallback" and not self.fallback_subtask_ids:
            return False, "fallback action requires non-empty fallback_subtask_ids"
        
        # Check for circular references (basic check)
        if self.local_id in self.depends_on:
            return False, f"subtask {self.local_id} cannot depend on itself"
        
        return True, None


class SubtaskIntentValidator(BaseModel):
    """
    Phase A2: Collection-level validator for SubtaskIntent instances.
    Checks for dependency consistency, circular references, and duplicates across intent collections.
    """
    
    @staticmethod
    def validate_intent_collection(intents: List[SubtaskIntent]) -> tuple[bool, List[str]]:
        """
        Validate a collection of SubtaskIntent instances.
        Checks for:
        - duplicate local_ids
        - circular dependencies
        - orphaned depends_on references
        - orphaned fallback_subtask_ids references
        
        Returns (is_valid, error_messages).
        """
        errors = []
        
        if not intents:
            return True, []
        
        # Check for duplicate local_ids
        local_ids = [intent.local_id for intent in intents]
        if len(local_ids) != len(set(local_ids)):
            duplicates = [id_ for id_ in local_ids if local_ids.count(id_) > 1]
            errors.append(f"Duplicate local_ids found: {set(duplicates)}")
        
        all_ids = set(local_ids)
        
        # Check for orphaned references
        for intent in intents:
            for dep_id in intent.depends_on:
                if dep_id not in all_ids:
                    errors.append(f"Subtask '{intent.local_id}' depends on unknown subtask '{dep_id}'")
            
            for fallback_id in intent.fallback_subtask_ids:
                if fallback_id not in all_ids:
                    errors.append(f"Subtask '{intent.local_id}' references unknown fallback subtask '{fallback_id}'")
        
        # Check for circular dependencies using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str, graph: Dict[str, List[str]]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, graph):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        # Build dependency graph
        graph = {intent.local_id: intent.depends_on for intent in intents}
        
        for intent in intents:
            if intent.local_id not in visited:
                if has_cycle(intent.local_id, graph):
                    errors.append(f"Circular dependency detected involving subtask '{intent.local_id}'")
        
        return len(errors) == 0, errors
