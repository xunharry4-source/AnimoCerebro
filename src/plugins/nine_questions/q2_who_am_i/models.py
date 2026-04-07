from __future__ import annotations
from typing import List


from pydantic import BaseModel, ConfigDict, Field


class RoleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_role: str = Field(min_length=1)
    active_role: str = Field(min_length=1)
    task_role: str = Field(min_length=1)


class MissionContinuityBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_mission: str = Field(min_length=1)
    priority_duties: List[str] = Field(default_factory=list)
    continuity_boundaries: List[str] = Field(default_factory=list, min_length=1)


class Q2WhoAmIInference(BaseModel):
    """
    Strict LLM output contract for Q2.

    Missing any field is a hard failure (fail-closed).
    """

    model_config = ConfigDict(extra="forbid")

    role_profile: RoleProfile
    mission_boundary: MissionContinuityBoundary

