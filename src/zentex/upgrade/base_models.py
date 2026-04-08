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
    """
    model_config = ConfigDict(extra="forbid")
    
    program_id: str = Field(..., description="Unique identifier for the upgrade program")
    target_metric: str = Field(..., description="Primary metric being optimized")
    baseline_version: str = Field(..., description="Current version being upgraded from")
    candidate_version: str = Field(..., description="Proposed new version")
    description: str = Field(default="", description="Human-readable description of changes")
    

class CandidatePatch(BaseModel):
    """
    Represents a patch or diff for a candidate upgrade.
    """
    model_config = ConfigDict(extra="forbid")
    
    patch_id: str = Field(..., description="Unique patch identifier")
    target_component: str = Field(..., description="Component being patched")
    changes: Dict[str, Any] = Field(default_factory=dict, description="Description of changes")
    risk_level: str = Field(default="medium", description="Risk assessment: low, medium, high")


class VerificationBundle(BaseModel):
    """
    Collection of verification results for a candidate.
    """
    model_config = ConfigDict(extra="forbid")
    
    bundle_id: str = Field(..., description="Unique bundle identifier")
    candidate_version: str = Field(..., description="Version being verified")
    test_results: List[Dict[str, Any]] = Field(default_factory=list, description="Test execution results")
    performance_metrics: Dict[str, float] = Field(default_factory=dict, description="Performance measurements")
    safety_checks_passed: bool = Field(default=False, description="Whether all safety checks passed")
    overall_status: str = Field(default="pending", description="pending, passed, failed")


class PromotionDecision(BaseModel):
    """
    Decision on whether to promote a candidate to production.
    """
    model_config = ConfigDict(extra="forbid")
    
    decision_id: str = Field(..., description="Unique decision identifier")
    candidate_version: str = Field(..., description="Version under consideration")
    action: str = Field(..., description="promote, reject, defer")
    rationale: str = Field(default="", description="Reasoning for the decision")
    conditions: List[str] = Field(default_factory=list, description="Conditions that must be met")
    timestamp: Optional[str] = Field(default=None, description="Decision timestamp")
