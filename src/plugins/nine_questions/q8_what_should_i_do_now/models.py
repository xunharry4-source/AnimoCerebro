from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Q8ObjectiveProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    current_mission: str = Field(min_length=1)
    mission_rationale: str = ""
    primary_objectives: list[str] = Field(default_factory=list)
    secondary_objectives: list[str] = Field(default_factory=list)
    completion_conditions: list[str] = Field(default_factory=list)
    pause_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)
    current_phase_tasks: list[str] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)


class Q8TaskQueue(BaseModel):
    model_config = ConfigDict(extra="allow")

    next_self_tasks: list[dict[str, Any]] = Field(default_factory=list)
    blocked_self_tasks: list[dict[str, Any]] = Field(default_factory=list)
    proactive_actions: list[dict[str, Any]] = Field(default_factory=list)


class Q8InferenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_profile: Q8ObjectiveProfile
    task_queue: Q8TaskQueue
