"""
Phase F: Observability Models

Data models for exposing routing decisions, verification results,
and supervision actions to external observers (frontend, logging, etc.)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ExecutorCandidateExplanation(BaseModel):
    """Explanation for why an executor was included/excluded from routing."""
    
    executor_id: str = Field(description="Executor ID")
    executor_type: str = Field(description="Type: internal plugin, MCP agent, external service")
    name: str = Field(description="Human-readable name")
    
    # Selection metrics
    is_healthy: bool = Field(description="Is this executor healthy?")
    capability_match_score: float = Field(ge=0.0, le=1.0, description="How well do capabilities match?")
    credit_score: float = Field(ge=0.0, le=10.0, description="Historical credit score")
    experience_success_rate: Optional[float] = Field(default=None, description="Success rate from history")
    
    # Reasoning
    selection_reason: str = Field(description="Why was this selected (or not)?")
    was_selected: bool = Field(description="Was this executor chosen?")
    ranking_position: int = Field(description="Rank among all candidates (1=best)")
    
    # Additional context
    fallback_chain_position: Optional[int] = Field(
        default=None, description="Position in fallback chain if selected"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DispatchExplanation(BaseModel):
    """Complete explanation for dispatch routing decision."""
    
    dispatch_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique ID for this dispatch")
    task_id: str = Field(description="Task being dispatched")
    task_type: str = Field(description="Task type")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Primary decision
    selected_executor_id: str = Field(description="Which executor was selected")
    selected_executor_name: str = Field(description="Name of selected executor")
    selection_rationale: str = Field(description="Why was this executor selected?")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in selection")
    
    # All candidates considered
    all_candidates: List[ExecutorCandidateExplanation] = Field(
        description="All candidates evaluated, ordered by ranking"
    )
    candidates_rejected_count: int = Field(description="How many were rejected?")
    rejection_reasons: List[str] = Field(description="Reasons candidates were rejected")
    
    # Process info
    internal_plugins_checked: int = Field(description="How many internal plugins checked?")
    internal_plugins_matched: int = Field(description="How many internal matched capability?")
    external_agents_checked: int = Field(description="How many external agents checked?")
    routing_algorithm: str = Field(description="Which routing algorithm was used?")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_display_text(self) -> str:
        """Format as human-readable explanation."""
        lines = [
            "=== DISPATCH DECISION ===",
            f"Task: {self.task_id} ({self.task_type})",
            f"Selected: {self.selected_executor_name}",
            f"Rationale: {self.selection_rationale}",
            f"Confidence: {self.confidence:.1%}",
            "",
            f"Candidates Evaluated: {len(self.all_candidates)}",
        ]
        
        for candidate in self.all_candidates[:3]:
            status = "✓ SELECTED" if candidate.was_selected else "✗"
            lines.append(f"  {status} {candidate.name} (rank #{candidate.ranking_position}, credit={candidate.credit_score:.1f})")
        
        if len(self.all_candidates) > 3:
            lines.append(f"  ... and {len(self.all_candidates) - 3} more")
        
        return "\n".join(lines)


class VerificationDetailExplanation(BaseModel):
    """Detailed explanation of verification results."""
    
    verification_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(description="Task that was verified")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Verification outcome
    verification_passed: bool = Field(description="Did verification pass?")
    verification_score: float = Field(ge=0.0, le=1.0, description="Verification score (0.0-1.0)")
    
    # If failed, detailed classification
    failure_type: Optional[str] = Field(default=None, description="Type of failure (if any)")
    failure_severity: Optional[str] = Field(default=None, description="HIGH/MEDIUM/LOW")
    failure_evidence: Optional[str] = Field(default=None, description="What evidence led to this classification?")
    
    # Lessons and recommendations
    lessons_learned: List[str] = Field(description="Patterns observed")
    recommended_actions: List[str] = Field(description="Recommended corrective actions")
    confidence_in_recommendations: float = Field(ge=0.0, le=1.0)
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_display_text(self) -> str:
        """Format as human-readable verification result."""
        status = "✅ PASSED" if self.verification_passed else "❌ FAILED"
        lines = [
            "=== VERIFICATION RESULT ===",
            f"Status: {status}",
            f"Score: {self.verification_score:.1%}",
        ]
        
        if self.failure_type:
            lines.extend([
                f"Failure Type: {self.failure_type}",
                f"Severity: {self.failure_severity}",
                f"Evidence: {self.failure_evidence}",
                "",
            ])
        
        if self.lessons_learned:
            lines.extend([
                "Lessons Learned:",
                "  " + "\n  ".join(f"• {l}" for l in self.lessons_learned[:3]),
            ])
        
        if self.recommended_actions:
            lines.extend([
                "Recommended Actions:",
                "  " + "\n  ".join(f"• {a}" for a in self.recommended_actions[:3]),
            ])
        
        return "\n".join(lines)


class SupervisionActionExplanation(BaseModel):
    """Explanation for a single supervision action."""
    
    action_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(description="Task being supervised")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Action details
    action_type: str = Field(description="RETRY, FALLBACK, ESCALATE, ABORT, etc.")
    action_reason: str = Field(description="Why was this action taken?")
    trigger_failure_type: str = Field(description="What failure triggered this?")
    
    # Action outcome
    action_executed: bool = Field(description="Was the action successfully executed?")
    action_result: Optional[str] = Field(default=None, description="What was the result?")
    
    # Next steps
    next_action_if_fails: Optional[str] = Field(default=None, description="What happens if this action fails?")
    estimated_recovery_time: Optional[int] = Field(default=None, description="Est. time to recover (seconds)")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_display_text(self) -> str:
        """Format as human-readable action explanation."""
        status = "✓" if self.action_executed else "✗"
        lines = [
            f"{status} {self.action_type}",
            f"  Reason: {self.action_reason}",
            f"  Triggered by: {self.trigger_failure_type}",
        ]
        
        if self.action_result:
            lines.append(f"  Result: {self.action_result}")
        
        if self.next_action_if_fails:
            lines.append(f"  Fallback: {self.next_action_if_fails}")
        
        return "\n".join(lines)


class SupervisionHistoryExplanation(BaseModel):
    """Complete history of supervision decisions for a task."""
    
    supervision_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(description="Task being supervised")
    start_time: datetime = Field(description="When supervision started")
    end_time: Optional[datetime] = Field(default=None, description="When supervision ended")
    
    # Supervision chain
    supervision_actions: List[SupervisionActionExplanation] = Field(
        description="All actions taken, in order"
    )
    total_attempts: int = Field(description="Total number of supervision attempts")
    
    # Overall outcome
    supervision_successful: bool = Field(description="Did supervision ultimately succeed?")
    final_status: str = Field(description="Final task status after supervision")
    
    # Lessons from supervision
    observations: List[str] = Field(description="Key observations from supervision chain")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_display_text(self) -> str:
        """Format as human-readable supervision history."""
        status = "✅ SUCCESS" if self.supervision_successful else "❌ UNSUCCESSFUL"
        lines = [
            "=== SUPERVISION HISTORY ===",
            f"Final Status: {status}",
            f"Actions Taken: {len(self.supervision_actions)}",
            "",
        ]
        
        for i, action in enumerate(self.supervision_actions, 1):
            lines.append(f"{i}. {action.to_display_text()}")
        
        return "\n".join(lines)
