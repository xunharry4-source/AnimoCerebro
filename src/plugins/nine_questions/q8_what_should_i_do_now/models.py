from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import Self
from pydantic import BaseModel, Field, ConfigDict


class ObjectiveProfile(BaseModel):
    """
    Q8 Result: Primary Objective and Phase Task breakdown.
    The ultimate synthetic decision of the Nine Questions cycle.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_primary_objective: str = Field(..., description="The highly condensed core focus for now.")
    current_phase_tasks: List[str] = Field(..., description="Step-by-step breakdown of the current phase.")
    priority_order: List[str] = Field(..., description="Explicit order of execution.")


class AutonomousTaskQueue(BaseModel):
    """
    Q8 Result: Task Distribution for the Self-Task Manager.
    Mandatory input source for src/zentex/tasks/registry.py.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    next_self_tasks: List[Dict[str, Any]] = Field(..., description="Tasks allowed within Q4/Q5 bounds.")
    blocked_self_tasks: List[Dict[str, Any]] = Field(..., description="Tasks currently blocked, with specific reasons (e.g., waiting for confirmation, lack of auth).")
    proactive_actions: List[Dict[str, Any]] = Field(..., description="Suggested proactive or exploratory steps.")


class Q8InferenceResult(BaseModel):
    """
    Strict LLM output contract for Q8.
    """
    model_config = ConfigDict(extra="forbid")

    objective_profile: ObjectiveProfile
    task_queue: AutonomousTaskQueue
