from __future__ import annotations
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class CapabilityBoundaryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_upper_limits: List[str] = Field(default_factory=list)
    actionable_space: List[str] = Field(default_factory=list)
    executable_strategies: List[str] = Field(default_factory=list)


class InferredCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_name: str
    capability_description: str
    used_q1_resources_and_q2_capabilities: "Q1Q2UsedResources"


class Q1Q2UsedResources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q1_resources: List[str] = Field(default_factory=list)
    q2_capabilities: List[str] = Field(default_factory=list)


class CapabilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inferred_capabilities: List[InferredCapability] = Field(default_factory=list)


class Q4WhatCanIDoInference(BaseModel):
    """
    Strict LLM output contract for Q4.
    """

    model_config = ConfigDict(extra="forbid")

    capability_assessment: CapabilityAssessment
    capability_boundary_profile: CapabilityBoundaryProfile | None = None
    permission_profile: Dict[str, Any] = Field(default_factory=dict)
