from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import Self
from pydantic import BaseModel, Field, ConfigDict


class ObjectiveProfile(BaseModel):
    """
    Q8 Result: Comprehensive Objective Profile.
    Includes primary/secondary objectives and lifecycle conditions.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_mission: str = Field(..., description="The highly condensed core focus for now.")
    mission_rationale: str = Field(default="", description="How the objective serves the upstream strategic mission.")
    basis_and_traceability: Dict[str, Any] = Field(default_factory=dict, description="Q1/Q2/Q5/Q6/Q7 isolated traceability arrays.")
    primary_objectives: List[str] = Field(default_factory=list, description="Top priority objectives.")
    secondary_objectives: List[str] = Field(default_factory=list, description="Lower priority or parallel objectives.")
    completion_conditions: List[str] = Field(default_factory=list, description="Conditions for success.")
    pause_conditions: List[str] = Field(default_factory=list, description="Conditions requiring a temporary halt.")
    escalation_conditions: List[str] = Field(default_factory=list, description="Conditions requiring human or higher-level intervention.")
    current_phase_tasks: List[str] = Field(default_factory=list, description="Specific tasks for the current phase.")
    priority_order: List[str] = Field(..., description="Explicit order of execution for current tasks.")


class AutonomousTaskQueue(BaseModel):
    """
    Q8 Result: Task Distribution for the Self-Task Manager.
    Mandatory input source for src/zentex/tasks/registry.py.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    next_self_tasks: List[Dict[str, Any]] = Field(..., description="Tasks allowed within validated permission and redline bounds.")
    blocked_self_tasks: List[Dict[str, Any]] = Field(..., description="Tasks currently blocked, with specific reasons (e.g., waiting for confirmation, lack of auth).")
    proactive_actions: List[Dict[str, Any]] = Field(..., description="Suggested proactive or exploratory steps.")


class Q8InferenceResult(BaseModel):
    """
    Strict LLM output contract for Q8.
    """
    model_config = ConfigDict(extra="forbid")

    objective_profile: ObjectiveProfile
    task_queue: AutonomousTaskQueue
