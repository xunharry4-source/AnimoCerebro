from __future__ import annotations
from typing import List


from pydantic import BaseModel, ConfigDict, Field


class RoleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_role: str = Field(min_length=1)
    active_role: str = Field(min_length=1)
    inferred_reference_role: str = Field(min_length=1)
    role_alignment_gap: str = Field(min_length=1)
    task_role: str = Field(min_length=1)


class MissionContinuityBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_mission: str = Field(min_length=1)
    priority_duties: List[str] = Field(default_factory=list, min_length=1)
    continuity_boundaries: List[str] = Field(default_factory=list, min_length=1)


class Q3InferenceResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    RoleProfile: RoleProfile
    MissionContinuityBoundary: MissionContinuityBoundary


class Q3WhoAmIInference(BaseModel):
    """
    Strict LLM output contract for Q3 role inference.
    """

    model_config = ConfigDict(extra="forbid")

    Q3InferenceResult: Q3InferenceResultPayload

    @property
    def role_profile(self) -> RoleProfile:
        return self.Q3InferenceResult.RoleProfile

    @property
    def mission_continuity_boundary(self) -> MissionContinuityBoundary:
        return self.Q3InferenceResult.MissionContinuityBoundary
