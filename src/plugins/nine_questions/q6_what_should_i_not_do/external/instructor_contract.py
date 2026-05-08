from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q6_external_instructor_not_installed") from exc


class ConsequenceAndCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    physical_side_effects: str = Field(min_length=1)
    blast_radius: str = Field(min_length=1)
    data_exposure_risk: str = Field(min_length=1)
    file_or_remote_mutation_risk: str = Field(min_length=1)
    monetary_cost: str = Field(min_length=1)
    compute_cost: str = Field(min_length=1)
    latency_cost: str = Field(min_length=1)
    rollback_difficulty: str = Field(min_length=1)


class ExecutionSafeguards(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read_only_probe_first: bool
    sandbox_first: bool
    dry_run_first: bool
    backup_required: bool
    confirmation_required: bool


class VerificationContracts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_requirements: str = Field(min_length=1)
    receipt_requirements: str = Field(min_length=1)


class HaltConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pause_conditions: str = Field(min_length=1)
    stop_conditions: str = Field(min_length=1)


class ExternalObjectiveConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_number: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    consequence_and_cost: ConsequenceAndCost
    execution_safeguards: ExecutionSafeguards
    verification_contracts: VerificationContracts
    halt_conditions: HaltConditions
    rationality_assessment: str = Field(min_length=1)


class ExternalPlanConstraintSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ExternalPlanConstraintSet"]
    objective_constraints: List[ExternalObjectiveConstraint] = Field(min_length=1)


def validate_external_plan_constraint_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = ExternalPlanConstraintSet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q6_external_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_external_plan_constraint_set_with_instructor_contract(
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
            "instructor_contract": "ExternalPlanConstraintSet",
            "response_model": "ExternalPlanConstraintSet",
        },
    )
    return validate_external_plan_constraint_set(raw_output)
