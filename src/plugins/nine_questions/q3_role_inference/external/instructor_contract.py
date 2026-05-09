from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q3_external_instructor_not_installed") from exc


class RoleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_name: str = Field(min_length=1)
    role_introduction: str = Field(min_length=1)


class ExternalExecutionIdentityHypothesisSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ExternalExecutionIdentityHypothesisSet"]
    ai_analyzed_role: RoleProfile
    human_set_role: RoleProfile
    candidate_external_roles: List[str] = Field(default_factory=list)
    external_role_conflicts: str = Field(min_length=1)
    delegation_posture: str = Field(min_length=1)
    operator_identity_constraints: str = Field(min_length=1)
    representation_limits: str = Field(min_length=1)
    recommended_external_posture: str = Field(min_length=1)


def validate_external_execution_identity_hypothesis_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = ExternalExecutionIdentityHypothesisSet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q3_external_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_external_execution_identity_hypothesis_set_with_instructor_contract(
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
            "instructor_contract": "ExternalExecutionIdentityHypothesisSet",
            "response_model": "ExternalExecutionIdentityHypothesisSet",
        },
    )
    return validate_external_execution_identity_hypothesis_set(raw_output)
