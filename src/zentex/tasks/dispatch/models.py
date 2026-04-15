"""
Phase B1: Dispatch models for task routing and execution coordination.
Defines the contract for internal/external executor selection decisions.

Routing Policy (per requirements):
- Internal: PluginLayer.FUNCTIONAL plugins (highest priority)
- External: MCP/AGENT/CLI executors (ranked by credit/quality evidence)
- Order: Try internal first; fall back to external if no match
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutorType(str, Enum):
    """Executor categories per routing policy"""
    INTERNAL_PLUGIN = "internal_plugin"  # PluginLayer.FUNCTIONAL
    EXTERNAL_MCP = "external_mcp"  # MCP executor
    EXTERNAL_AGENT = "external_agent"  # AGENT executor
    EXTERNAL_CLI = "external_cli"  # CLI executor


class ExecutorCandidate(BaseModel):
    """
    Phase B1: Single candidate executor for a subtask.
    Represents all available information for ranking executor selection.
    """
    # Identity & type
    executor_id: str = Field(description="Unique executor identifier (e.g. uuid, plugin_name, mcp_id)")
    executor_type: ExecutorType = Field(description="Executor category: internal/external")
    executor_name: str = Field(description="Human-readable name")
    
    # Capability matching
    has_required_capabilities: bool = Field(
        description="Whether executor has all required_capabilities from subtask"
    )
    capability_match_score: float = Field(
        ge=0.0, le=1.0,
        description="Score 0-1 representing how well executor matches subtask requirements"
    )
    
    # Health & quality evidence
    is_healthy: bool = Field(description="Whether executor is currently active/healthy")
    success_rate: float = Field(
        ge=0.0, le=1.0,
        description="Historical success rate (fraction of successful executions)"
    )
    average_execution_time_seconds: Optional[float] = Field(
        default=None,
        description="Average execution time for similar tasks"
    )
    
    # Credit/reputation system
    credit_score: float = Field(
        ge=0.0,
        description="Reputation/credit score from historical performance"
    )
    times_selected: int = Field(
        ge=0,
        description="How many times this executor has been selected"
    )
    times_succeeded: int = Field(
        ge=0,
        description="How many times this executor's task succeeded"
    )
    
    # Metadata for routing decisions
    priority_rank: int = Field(
        ge=0,
        description="Execution priority (0=highest). Internal plugins default to 0; external ranked by credit"
    )
    routing_reason: str = Field(
        description="Why this executor was considered (e.g. 'matches capability X', 'high success rate')"
    )


class DispatchDecision(BaseModel):
    """
    Phase B1: Outcome of dispatch selection logic.
    Represents the chosen executor and rationale for routing decision.
    """
    # Decision metadata
    task_id: str = Field(description="Task being dispatched")
    decision_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Chosen executor
    selected_executor: ExecutorCandidate = Field(
        description="The executor chosen for this task"
    )
    
    # Alternatives (for debugging/escalation)
    candidate_pool: List[ExecutorCandidate] = Field(
        default_factory=list,
        description="All candidates considered (for audit trail)"
    )
    
    # Decision rationale
    decision_logic: str = Field(
        description="Which logic path was used: 'internal_match', 'internal_fallback', 'external_best', 'no_match_escalate'"
    )
    fallback_chain: List[str] = Field(
        default_factory=list,
        description="Executor IDs in order of fallback preference (if selected fails)"
    )
    
    # Constraints applied
    allowed_executor_types: Optional[List[ExecutorType]] = Field(
        default=None,
        description="Executor type constraints from subtask (None = no constraints)"
    )
    required_capabilities: List[str] = Field(
        default_factory=list,
        description="Capabilities required by the subtask"
    )


class DispatchResult(BaseModel):
    """
    Phase B1: Result of task execution after dispatch.
    Represents the outcome and failure handling action.
    """
    # Execution metadata
    task_id: str = Field(description="Task that was executed")
    executor_id: str = Field(description="Executor that handled the task")
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_duration_seconds: float = Field(
        ge=0,
        description="How long the execution took"
    )
    
    # Execution outcome
    succeeded: bool = Field(description="Whether execution succeeded")
    output: Optional[Any] = Field(
        default=None,
        description="Task output (if succeeded)"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message (if failed)"
    )
    
    # Failure handling decision
    failure_action: str = Field(
        description="Action to take if task failed: retry, skip, fallback, escalate, or abort_parent"
    )
    next_executor_id: Optional[str] = Field(
        default=None,
        description="ID of executor to try next (if failure_action=fallback)"
    )
    
    # Metadata for feedback loop
    failure_classification: Optional[str] = Field(
        default=None,
        description="Type of failure (e.g. capability_mismatch, timeout, resource_error)"
    )
    learning_signals: Dict[str, Any] = Field(
        default_factory=dict,
        description="Signals for updating executor credit scores (e.g. {success_rate_delta: 0.05})"
    )
