from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ObjectiveProfile(BaseModel):
    """
    Objective Profile: Represents what the system should pursue at the current stage.
    Derived from Q2 (Role), Q3 (Assets), and Q8 (What should I do).
    """
    model_config = ConfigDict(extra="forbid")

    current_mission: str = Field(..., description="Current primary mission or the main thread task for this turn.")
    primary_objectives: List[str] = Field(default_factory=list, description="List of highest priority objectives.")
    secondary_objectives: List[str] = Field(default_factory=list, description="Secondary objectives to consider in parallel.")
    completion_conditions: List[str] = Field(default_factory=list, description="Conditions that signify target completion.")
    pause_conditions: List[str] = Field(default_factory=list, description="Conditions that mandate pausing the objective.")
    escalation_conditions: List[str] = Field(default_factory=list, description="Conditions that mandate escalation to human or higher-level Agent.")


class EvaluationProfile(BaseModel):
    """
    Evaluation Profile: Defines the criteria for 'good' vs 'bad' results in the current context.
    Derived from Q3/Q4 (Resources), Q7 (Risk), and Q5 (Auth).
    """
    model_config = ConfigDict(extra="forbid")

    role_context: str = Field(..., description="Current role context (e.g., auditor, creator, orchestrator).")
    resource_context: str = Field(..., description="Context of available resources: budget, tools, time.")
    risk_level: str = Field(..., description="Current overall risk level.")
    evaluation_weights: Dict[str, float] = Field(
        default_factory=lambda: {"accuracy": 0.2, "speed": 0.2, "risk_control": 0.2, "creativity": 0.2, "continuity": 0.2},
        description="Weights for various evaluation dimensions."
    )
    conservative_mode_triggered: bool = Field(default=False, description="Whether conservative mode has been activated due to uncertainty or risk.")
    evaluation_style: str = Field(default="balanced", description="The logic/evidence threshold for actions.")


class EvolutionProfile(BaseModel):
    """
    Evolution Profile: Defines allowed directions for self-optimization and evolution.
    Derived from Q4 (Capabilities), Q6 (Evolution directions), and Q7 (Redlines).
    """
    model_config = ConfigDict(extra="forbid")

    allowed_directions: List[str] = Field(default_factory=list, description="Permitted directions for ability expansion or structural optimization.")
    risk_threshold: float = Field(default=0.1, description="Acceptable risk threshold for evolution (0.0 to 1.0).")
    forbidden_directions: List[str] = Field(default_factory=list, description="Explicitly forbidden directions (e.g., safety chain, identity kernel).")
    validation_requirements: List[str] = Field(default_factory=list, description="Required validations before evolution can be finalized.")


class EscalationProfile(BaseModel):
    """
    Escalation Profile: Defines when to pause, seek help, confirm, or rollback.
    Derived from overall state and Nine-Question synthesis.
    """
    model_config = ConfigDict(extra="forbid")

    pause_conditions: List[str] = Field(default_factory=list, description="Conditions for pausing execution.")
    help_request_conditions: List[str] = Field(default_factory=list, description="Conditions for requesting help from humans or other Agents.")
    confirmation_required_conditions: List[str] = Field(default_factory=list, description="Conditions that strictly require manual confirmation.")
    revisit_conditions: List[str] = Field(default_factory=list, description="Conditions that mandate re-evaluating the Nine Questions.")
    rollback_conditions: List[str] = Field(default_factory=list, description="Conditions that require rolling back the current plan or evolution.")


class Phase2EvolutionResult(BaseModel):
    """
    Consolidated result of Phase 2 Subject Evolution derivation.
    """
    model_config = ConfigDict(extra="forbid")

    objective: ObjectiveProfile
    evaluation: EvaluationProfile
    evolution: EvolutionProfile
    escalation: EscalationProfile
    timestamp: str
    snapshot_version: int
    question_driver_refs: Dict[str, List[str]] = Field(
        default_factory=dict, 
        description="Mapping of profile fields or categories to the questions that drove them (traceability)."
    )
