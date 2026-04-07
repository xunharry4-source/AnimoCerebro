from __future__ import annotations
from typing import List


from pydantic import BaseModel, ConfigDict, Field


class CapabilityBoundaryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_upper_limits: List[str] = Field(default_factory=list)
    actionable_space: List[str] = Field(default_factory=list)
    executable_strategies: List[str] = Field(default_factory=list)


class Q4WhatCanIDoInference(BaseModel):
    """
    Strict LLM output contract for Q4.
    """

    model_config = ConfigDict(extra="forbid")

    capability_boundary_profile: CapabilityBoundaryProfile

