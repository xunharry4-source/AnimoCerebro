from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q6_internal_instructor_not_installed") from exc


class InternalObjectiveConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_number: str = Field(min_length=1)
    objective_reference: str = Field(min_length=1)
    cognitive_cost: str = Field(min_length=1)
    memory_impact: str = Field(min_length=1)
    reflection_overuse_risk: str = Field(min_length=1)
    learning_overfit_risk: str = Field(min_length=1)
    value_drift_risk: str = Field(min_length=1)
    strategy_pollution_risk: str = Field(min_length=1)
    self_evolution_failure_modes: str = Field(min_length=1)
    sandbox_requirements: str = Field(min_length=1)
    verification_requirements: str = Field(min_length=1)
    pause_conditions: str = Field(min_length=1)
    stop_conditions: str = Field(min_length=1)
    rollback_requirements: str = Field(min_length=1)
    must_avoid: List[str] = Field(min_length=1, max_length=3)


class InternalPlanConstraintSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["InternalPlanConstraintSet"]
    constraints_by_objective: List[InternalObjectiveConstraint] = Field(min_length=1)


def validate_internal_plan_constraint_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = InternalPlanConstraintSet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q6_internal_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_internal_plan_constraint_set_with_instructor_contract(
    provider: Any,
    *,
    prompt: str,
    context: dict[str, Any],
    caller_context: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_instructor_runtime()
    raw_output = provider.generate_json(
        prompt=prompt,
        context=context,
        caller_context=caller_context,
        metadata={
            **(metadata or {}),
            "instructor_contract": "InternalPlanConstraintSet",
            "response_model": "InternalPlanConstraintSet",
        },
    )
    return validate_internal_plan_constraint_set(raw_output)
