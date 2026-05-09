from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

ExternalObjectiveType = Literal[
    "agent_delegation_objectives",
    "cli_objectives",
    "mcp_objectives",
    "connector_objectives",
    "external_service_objectives",
    "file_or_office_objectives",
    "browser_or_saas_objectives",
    "information_acquisition_objectives",
    "external_problem_solving_objectives",
]

_VARIABLE_PLACEHOLDERS = (
    "Q1_EnvironmentObjectiveSignal_External",
    "Q2_SelfObservationObjectiveSignal_External",
    "Q3_ExternalDelegationPosture",
    "Reflection_CapabilityGapSignal_External",
    "CapabilityBoundaryEvidence_External",
    "Q1Q2_FusedObjectiveSignal_External",
    "UserManualTaskGoalLaneAnalysis",
    "Q1 变量",
    "Q2 变量",
    "Q3 变量",
    "Reflection 变量",
    "CapabilityBoundary 变量",
    "{{",
    "}}",
)
_PLACEHOLDER_PREFIXES = (
    "Q1_",
    "Q2_",
    "Q3_",
    "Reflection_",
    "CapabilityBoundary",
    "Q1Q2_",
    "UserManualTaskGoalLaneAnalysis",
)
_FORBIDDEN_EXECUTION_IDENTIFIERS = ("task_id", "subtask_id")
_PLAN_STEP_MARKUP_PATTERN = re.compile(
    r"(?:^|[\r\n])\s*(?:\d+[\.)]|[一二三四五六七八九十]+[、.)]|[-*•])\s+\S"
)
_PLAN_STEP_WORD_PATTERN = re.compile(r"(?:第一步|第二步|第三步|步骤\s*\d+|step\s*\d+)", re.IGNORECASE)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q4_external_instructor_not_installed") from exc


def _contains_placeholder(value: str) -> bool:
    return any(item in value for item in _VARIABLE_PLACEHOLDERS) or any(
        value.strip().startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES
    )


def _reject_placeholder(value: str, *, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name}_empty")
    if _contains_placeholder(text):
        raise ValueError(f"{field_name}_contains_unexpanded_variable")
    return text


def _contains_plan_step_markup(value: str) -> bool:
    if "\n" in value or "\r" in value:
        return True
    return bool(_PLAN_STEP_MARKUP_PATTERN.search(value) or _PLAN_STEP_WORD_PATTERN.search(value))


class ExternalObjectiveCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_number: str = Field(
        ...,
        min_length=1,
        pattern=r"^Q4-E-\d{3}$",
        description="Stable external Q4 objective identifier, e.g. Q4-E-001. Must not be objective_type or task_id.",
    )
    objective_type: ExternalObjectiveType
    capability_evidence_refs: list[str] = Field(default_factory=list)
    signal_or_gap_addressed: str
    objective_rationale: str
    candidate_description: str

    @field_validator("capability_evidence_refs")
    @classmethod
    def _validate_capability_refs(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("capability_evidence_refs_empty")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("capability_evidence_refs_item_not_string")
            text = _reject_placeholder(item, field_name="capability_evidence_refs")
            if text not in seen:
                normalized.append(text)
                seen.add(text)
        if not normalized:
            raise ValueError("capability_evidence_refs_empty")
        return normalized

    @field_validator("signal_or_gap_addressed", "objective_rationale")
    @classmethod
    def _validate_trace_fields(cls, value: str, info: Any) -> str:
        return _reject_placeholder(value, field_name=str(info.field_name))

    @field_validator("objective_number")
    @classmethod
    def _validate_objective_number(cls, value: str) -> str:
        text = _reject_placeholder(value, field_name="objective_number")
        lowered = text.lower()
        if any(identifier in lowered for identifier in _FORBIDDEN_EXECUTION_IDENTIFIERS):
            raise ValueError("objective_number_contains_execution_identifier")
        if text in ExternalObjectiveType.__args__:
            raise ValueError("objective_number_must_not_be_objective_type")
        return text

    @field_validator("candidate_description")
    @classmethod
    def _validate_candidate_description(cls, value: str) -> str:
        text = _reject_placeholder(value, field_name="candidate_description")
        lowered = text.lower()
        if any(identifier in lowered for identifier in _FORBIDDEN_EXECUTION_IDENTIFIERS):
            raise ValueError("candidate_description_contains_execution_identifier")
        if _contains_plan_step_markup(text):
            raise ValueError("candidate_description_contains_plan_steps")
        return text

    @model_validator(mode="after")
    def _validate_business_goal_shape(self) -> ExternalObjectiveCandidate:
        if self.candidate_description == self.signal_or_gap_addressed:
            raise ValueError("candidate_description_must_not_copy_signal")
        return self


class ExternalObjectiveCandidateSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ExternalObjectiveCandidateSet"]
    objective_candidates: list[ExternalObjectiveCandidate] = Field(
        ...,
        min_length=5,
        description="强制红线：必须包含至少 5 个以上的宏观业务目标候选。如果生成数量少于 5 个，系统将直接拦截并判定为推理不合格。",
    )

    @model_validator(mode="after")
    def _validate_objective_numbers_unique(self) -> ExternalObjectiveCandidateSet:
        numbers = [candidate.objective_number for candidate in self.objective_candidates]
        if len(numbers) != len(set(numbers)):
            raise ValueError("objective_number_duplicate")
        return self


def validate_external_objective_candidate_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    payload = raw_output
    try:
        validated = ExternalObjectiveCandidateSet.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"q4_external_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_external_objective_candidate_set_with_instructor_contract(
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
            "instructor_contract": "ExternalObjectiveCandidateSet",
            "response_model": "ExternalObjectiveCandidateSet",
        },
    )
    return validate_external_objective_candidate_set(raw_output)
