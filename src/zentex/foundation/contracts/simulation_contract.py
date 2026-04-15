"""Simulation contracts — branch, intent and result models."""

from uuid import uuid4

from pydantic import Field

from zentex.foundation.contracts.base_models import ZentexBaseModel


class SimulationBranch(ZentexBaseModel):
    """A single hypothetical outcome branch in a simulation."""

    branch_id: str = Field(default_factory=lambda: str(uuid4()))
    description: str
    probability: float = 0.5
    side_effect_risk: float = 0.0
    steps: list[str] = Field(default_factory=list)


class SimulationIntent(ZentexBaseModel):
    """Specification for a simulation run."""

    intent_id: str = Field(default_factory=lambda: str(uuid4()))
    scenario: str
    conditions: dict = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)


class SimulationResult(ZentexBaseModel):
    """Aggregated result of a completed simulation."""

    intent_id: str
    branches: list[SimulationBranch] = Field(default_factory=list)
    confidence: float = 0.0
    recommended_branch_id: str = ""
    duration_ms: float = 0.0
