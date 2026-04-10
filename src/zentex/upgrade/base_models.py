from __future__ import annotations

"""
Base models for self-upgrade system.

These are shared base classes used across LLM and plugin upgrade systems.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class UpgradeTargetKind(str, Enum):
    """Target type for self-upgrade operations."""
    LLM = "llm"
    PLUGIN = "plugin"
    COGNITIVE_TOOL = "cognitive_tool"
    RUNTIME_COMPONENT = "runtime_component"


class SelfUpgradeProposal(BaseModel):
    """
    Base proposal for self-upgrade operations.
    
    Represents a candidate change that needs validation before promotion.
    Includes G25 nine-question audit fields for compliance.
    """
    model_config = ConfigDict(extra="forbid")
    
    # Core identification fields
    program_id: str = Field(..., description="Unique identifier for the upgrade program")
    target_metric: str = Field(..., description="Primary metric being optimized")
    baseline_version: str = Field(..., description="Current version being upgraded from")
    candidate_version: str = Field(..., description="Proposed new version")
    description: str = Field(default="", description="Human-readable description of changes")
    
    # Risk assessment fields (for G25 audit)
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Impact assessment (0-1)")
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Risk assessment (0-1)")
    occurrence_count: int = Field(default=1, ge=1, description="Number of occurrences triggering this proposal")
    
    # Capability gap description
    capability_gap: str = Field(default="", description="Description of the capability gap")
    proposed_changes: List[str] = Field(default_factory=list, description="Proposed changes to address the gap")
    affected_modules: List[str] = Field(default_factory=list, description="Modules affected by this upgrade")
    
    # G25 nine-question audit results
    g25_q1_necessity: bool = Field(default=False, description="Q1: Is upgrade necessary?")
    g25_q2_risk_acceptable: bool = Field(default=False, description="Q2: Is risk acceptable?")
    g25_q3_impact_assessed: bool = Field(default=False, description="Q3: Is impact assessed?")
    g25_q4_rollback_plan: bool = Field(default=False, description="Q4: Is rollback plan ready?")
    g25_q5_validation_complete: bool = Field(default=False, description="Q5: Is validation complete?")
    g25_q6_compliance: bool = Field(default=False, description="Q6: Is it compliant?")
    g25_q7_performance: bool = Field(default=False, description="Q7: Is performance acceptable?")
    g25_q8_dependencies: bool = Field(default=False, description="Q8: Are dependencies managed?")
    g25_q9_maintainability: bool = Field(default=False, description="Q9: Is it maintainable?")
    
    # Overall G25 audit result
    g25_audit_verified: bool = Field(default=False, description="Overall G25 audit result")
    g25_audit_details: Dict[str, Any] = Field(default_factory=dict, description="Detailed G25 audit results")
    

class CandidatePatch(BaseModel):
    """
    Represents a patch or diff for a candidate upgrade.
    Includes sandbox verification fields for isolated testing.
    """
    model_config = ConfigDict(extra="forbid")
    
    patch_id: str = Field(..., description="Unique patch identifier")
    target_component: str = Field(..., description="Component being patched")
    changes: Dict[str, Any] = Field(default_factory=dict, description="Description of changes")
    risk_level: str = Field(default="medium", description="Risk assessment: low, medium, high")
    
    # Sandbox verification fields
    isolation_path: str = Field(default="", description="Path to isolated sandbox directory")
    validation_commands: List[str] = Field(default_factory=list, description="Commands to run in sandbox")
    source_path: str = Field(default="", description="Original source path before copying")


class VerificationBundle(BaseModel):
    """
    Collection of verification results for a candidate.
    Includes detailed test results for each verification stage.
    """
    model_config = ConfigDict(extra="forbid")
    
    bundle_id: str = Field(..., description="Unique bundle identifier")
    candidate_version: str = Field(..., description="Version being verified")
    test_results: List[Dict[str, Any]] = Field(default_factory=list, description="Test execution results")
    performance_metrics: Dict[str, float] = Field(default_factory=dict, description="Performance measurements")
    safety_checks_passed: bool = Field(default=False, description="Whether all safety checks passed")
    overall_status: str = Field(default="pending", description="pending, passed, failed")
    
    # Detailed verification results for each stage
    lint_result: Optional[Dict[str, Any]] = Field(default=None, description="Lint check result")
    test_result: Optional[Dict[str, Any]] = Field(default=None, description="Test execution result")
    typecheck_result: Optional[Dict[str, Any]] = Field(default=None, description="Type check result")
    build_result: Optional[Dict[str, Any]] = Field(default=None, description="Build result")
    interface_check_result: Optional[Dict[str, Any]] = Field(default=None, description="Interface compatibility check")
    
    # Status tracking
    verification_status: str = Field(default="pending", description="pending/running/completed/failed")
    overall_verdict: str = Field(default="pending", description="pass/fail")


class PromotionDecision(BaseModel):
    """
    Decision on whether to promote a candidate to production.
    Includes G25 audit confirmation and reviewer tracking.
    """
    model_config = ConfigDict(extra="forbid")
    
    decision_id: str = Field(..., description="Unique decision identifier")
    candidate_version: str = Field(..., description="Version under consideration")
    action: str = Field(..., description="promote, reject, defer")
    rationale: str = Field(default="", description="Reasoning for the decision")
    conditions: List[str] = Field(default_factory=list, description="Conditions that must be met")
    timestamp: Optional[str] = Field(default=None, description="Decision timestamp")
    
    # G25 audit fields
    reviewer_id: str = Field(default="G25_audit", description="Reviewer identifier")
    confirmed_by_g25: bool = Field(default=False, description="Whether G25 audit confirmed")
    final_version: str = Field(default="", description="Final version after promotion")
    
    # Candidate reference
    candidate_id: str = Field(default="", description="Candidate patch ID")
