from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q5_external_instructor_not_installed") from exc


class BlockedExternalObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_number: str = Field(min_length=1, pattern=r"^Q4-E-\d{3}$")
    objective: str = Field(min_length=1)
    violation_reason: str = Field(min_length=1)


class AllowedExternalObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_number: str = Field(min_length=1, pattern=r"^Q4-E-\d{3}$")
    objective: str = Field(min_length=1)
    compliance_condition: str = Field(min_length=1)


class ExternalGoalComplianceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ExternalGoalComplianceAssessment"]
    system_safety_boundary: str = Field(min_length=1)
    blocked_external_objectives: List[BlockedExternalObjective] = Field(default_factory=list)
    requires_cloud_audit: List[str] = Field(default_factory=list)
    requires_human_confirmation: List[str] = Field(default_factory=list)
    permission_boundary_hits: List[str] = Field(default_factory=list)
    data_exfiltration_risks: List[str] = Field(default_factory=list)
    unauthorized_mutation_risks: List[str] = Field(default_factory=list)
    allowed_external_objectives_with_conditions: List[AllowedExternalObjective] = Field(default_factory=list)


def _extract_q4_external_objective_numbers(context: dict[str, Any]) -> set[str]:
    prompt_context = context.get("context") if isinstance(context, dict) else {}
    if not isinstance(prompt_context, dict):
        return set()
    q4_payload = prompt_context.get("Q4_ExternalObjectiveCandidates")
    if not isinstance(q4_payload, dict):
        return set()
    candidate_set = q4_payload.get("candidate_set") or q4_payload
    candidates = candidate_set.get("objective_candidates") if isinstance(candidate_set, dict) else None
    if not isinstance(candidates, list):
        return set()
    return {
        str(candidate.get("objective_number") or "").strip()
        for candidate in candidates
        if isinstance(candidate, dict) and str(candidate.get("objective_number") or "").strip()
    }


def validate_external_goal_compliance_assessment(
    raw_output: dict[str, Any],
    *,
    q4_objective_numbers: set[str] | None = None,
) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = ExternalGoalComplianceAssessment.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q5_external_instructor_validation_failed:{exc}") from exc
    payload = validated.model_dump(mode="json")
    if q4_objective_numbers is not None:
        output_numbers = {
            str(item.get("objective_number") or "").strip()
            for key in ("blocked_external_objectives", "allowed_external_objectives_with_conditions")
            for item in payload.get(key, [])
            if isinstance(item, dict)
        }
        unknown_numbers = sorted(number for number in output_numbers if number not in q4_objective_numbers)
        if unknown_numbers:
            raise RuntimeError(
                "q5_external_instructor_validation_failed:"
                f"objective_number_not_in_q4_candidates:{','.join(unknown_numbers)}"
            )
    return payload


def generate_external_goal_compliance_assessment_with_instructor_contract(
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
            "instructor_contract": "ExternalGoalComplianceAssessment",
            "response_model": "ExternalGoalComplianceAssessment",
        },
    )
    return validate_external_goal_compliance_assessment(
        raw_output,
        q4_objective_numbers=_extract_q4_external_objective_numbers(context),
    )
