from __future__ import annotations
"""
Task Reanalysis Models - Handle partial completion and improvement opportunities.
Detects when tasks are stuck mid-execution or can be improved after completion.

Scenarios:
1. Partial Completion: Task execution stops at subtask N out of M (stuck)
2. Post-Completion Analysis: Task finished, but analysis suggests improvements
3. Incremental Refinement: New tasks generated to continue from stop point
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PartialCompletionReason(str, Enum):
    """Reasons why a task stopped mid-execution"""
    EXECUTOR_TIMEOUT = "executor_timeout"  # Executor exceeded time limit
    EXECUTOR_UNAVAILABLE = "executor_unavailable"  # No executor available for next step
    DEPENDENCY_BLOCKED = "dependency_blocked"  # Dependency chain broken
    CAPABILITY_MISMATCH = "capability_mismatch"  # Required capability not available
    RESOURCE_EXHAUSTED = "resource_exhausted"  # Memory/compute exhausted
    MANUAL_SUSPENSION = "manual_suspension"  # Human intervention
    CASCADING_FAILURE = "cascading_failure"  # Previous step failure blocked progress


class PartialCompletion(BaseModel):
    """
    Represents a task that stopped execution mid-way.
    Captures where it stopped and why, enabling continuation or restart.
    """
    task_id: str = Field(description="Original task ID")
    mission_id: str = Field(description="Parent mission ID")
    
    # Completion status
    completed_subtask_count: int = Field(description="Number of subtasks completed successfully")
    total_subtask_count: int = Field(description="Total subtasks in original decomposition")
    completion_percentage: float = Field(
        ge=0, le=100,
        description="Percentage of task completed"
    )
    
    # Stop point details
    stopped_at_subtask_index: int = Field(
        description="Index of subtask where execution stopped (0-indexed)"
    )
    stopped_at_local_id: str = Field(
        description="Local ID of the subtask that failed/timed out"
    )
    stop_reason: PartialCompletionReason = Field(
        description="Why execution stopped"
    )
    
    # Recovery information
    last_successful_subtask_index: int = Field(
        description="Index of last successfully completed subtask"
    )
    completed_output: Dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregated output from completed subtasks"
    )
    error_context: Optional[str] = Field(
        default=None,
        description="Error message from failing executor"
    )
    
    # Metadata
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_execution_time_seconds: float = Field(
        description="How long task ran before stopping"
    )


class ImprovementSuggestion(BaseModel):
    """
    Analysis of task completion - identifies optimization opportunities.
    Generated after successful task completion.
    """
    task_id: str = Field(description="Completed task ID")
    mission_id: str = Field(description="Parent mission ID")
    
    # Analysis results
    suggestion_type: str = Field(
        description="Type of improvement: optimization, refinement, extension, alternative_approach"
    )
    confidence_score: float = Field(
        ge=0, le=1,
        description="Confidence in this suggestion (0-1)"
    )
    
    # Improvement details
    description: str = Field(
        description="What can be improved and why"
    )
    expected_benefit: str = Field(
        description="Expected benefit (e.g., 'faster', 'more accurate', 'broader scope')"
    )
    
    # New task specification
    suggested_new_subtasks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Potential subtasks to add for improvement"
    )
    estimated_additional_effort: str = Field(
        description="Time/resource estimate for improvement (e.g., '5 minutes', 'minimal')"
    )
    
    # Context for decision-making
    related_execution_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metrics from original execution (e.g., success_rate, time_spent, resources_used)"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReanalysisPlan(BaseModel):
    """
    Decision to reanalyze a task (either for continuation or improvement).
    Specifies what new decomposition should be generated.
    """
    # Reference to original task
    original_task_id: str = Field(description="Task being reanalyzed")
    original_mission_id: str = Field(description="Parent mission")
    
    # Decision metadata
    reanalysis_type: str = Field(
        description="Type: continue_from_stop, improve_completion, or alternative_path"
    )
    decision_reason: str = Field(
        description="Why reanalysis is needed (e.g., 'task blocked at subtask 2', 'efficiency improvement identified')"
    )
    
    # Context for new decomposition
    completed_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Output/state from completed portions (feeds into new decomposition)"
    )
    failure_analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Analysis of what failed and how to avoid (if continuation)"
    )
    improvement_goals: List[str] = Field(
        default_factory=list,
        description="Goals for the new decomposition (e.g., 'add verification step', 'parallelize where possible')"
    )
    
    # Constraints for new decomposition
    reuse_completed_results: bool = Field(
        default=True,
        description="Whether to reuse results from completed subtasks"
    )
    max_new_subtasks: Optional[int] = Field(
        default=None,
        description="Limit on new subtasks to add (None = unlimited)"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    related_improvement_suggestion_id: Optional[str] = Field(
        default=None,
        description="If originated from improvement suggestion, reference it"
    )


class ReanalysisResult(BaseModel):
    """
    Output of reanalysis - new decomposition and continuation plan.
    """
    # Reference
    original_task_id: str = Field(description="Task being reanalyzed")
    reanalysis_plan_id: str = Field(description="Plan that triggered this reanalysis")
    
    # New decomposition
    new_subtasks: List[Dict[str, Any]] = Field(
        description="New subtask list (continuation or improvement)"
    )
    
    # Continuation logic
    resume_from_index: Optional[int] = Field(
        default=None,
        description="If continuation, which original subtask to skip (resume after this)"
    )
    continuation_handoff_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Data to pass from completed tasks to new ones"
    )
    
    # New task specs
    generated_new_mission_id: Optional[str] = Field(
        default=None,
        description="ID of generated new mission task (if creating separate task)"
    )
    relationship_to_original: str = Field(
        default="sibling",
        description="How new task relates: sibling (parallel improvement) or child (continuation)"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decomposer_used: str = Field(
        description="Which decomposer was used (mock/llm/semantic_kernel)"
    )
