from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q8_internal_instructor_not_installed") from exc


class Q1Basis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment_signal_name: str = Field(min_length=1)
    trigger_reason: str = Field(min_length=1)


class Q2Basis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_function_name: str = Field(min_length=1)
    support_logic: str = Field(min_length=1)


class Q3Basis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability_name: str = Field(min_length=1)
    posture_adjustment: str = Field(min_length=1)


class Q7Basis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checked_risk_point: str = Field(min_length=1)
    compliance_reason: str = Field(min_length=1)


class BasisAndTraceability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q1_environment_bases: List[Q1Basis] = Field(min_length=1)
    q2_asset_support_bases: List[Q2Basis] = Field(min_length=1)
    q3_role_alignment: List[Q3Basis] = Field(min_length=1)
    q7_boundary_checks: List[Q7Basis] = Field(min_length=1)


class ObjectiveProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_mission: str = Field(min_length=1)
    basis_and_traceability: BasisAndTraceability
    primary_objectives: List[str] = Field(min_length=1)
    secondary_objectives: List[str] = Field(default_factory=list)
    completion_conditions: List[str] = Field(min_length=1)
    pause_conditions: List[str] = Field(default_factory=list)
    escalation_conditions: List[str] = Field(default_factory=list)


class InternalObjectiveProfileRoot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ObjectiveProfile: ObjectiveProfile


def validate_internal_objective_profile(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = InternalObjectiveProfileRoot.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q8_internal_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_internal_objective_profile_with_instructor_contract(
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
            "instructor_contract": "InternalObjectiveProfileRoot",
            "response_model": "InternalObjectiveProfileRoot",
        },
    )
    return validate_internal_objective_profile(raw_output)
