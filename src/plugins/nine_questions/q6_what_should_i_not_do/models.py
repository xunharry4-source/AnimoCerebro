from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field


class ForbiddenZoneProfile(BaseModel):
    """
    Zentex Q6: 我即使能做也不该做什么 (red-lines and forbidden zones).
    This model defines the moral and strategic guardrails derived from 
    long-term mission values and identity constraints.
    """
    model_config = ConfigDict(extra="forbid")

    absolute_red_lines: List[str] = Field(
        default_factory=list, 
        description="Absolute constraints that must never be bypassed (e.g. 'no modification of system config')."
    )
    performance_tradeoff_bans: List[str] = Field(
        default_factory=list,
        description="Bans on sacrificing safety for performance/success (e.g. 'no skipping cloud audit')."
    )
    prohibited_strategies: List[str] = Field(
        default_factory=list,
        description="Strategically sound but ethically/mission-wise rejected plans."
    )
    contamination_risks: List[str] = Field(
        default_factory=list,
        description="Risks of identity pollution or unauthorized credential leakage."
    )


class Q6InferenceResult(BaseModel):
    """
    Unified output for Zentex cognitive phase 6.
    """
    model_config = ConfigDict(extra="forbid")

    forbidden_zone_profile: ForbiddenZoneProfile
