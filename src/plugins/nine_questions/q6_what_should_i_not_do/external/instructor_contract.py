from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)
Q6_EXTERNAL_INSTRUCTOR_MAX_ATTEMPTS = 3


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


def _normalize_expected_objective_numbers(values: list[str] | None) -> list[str]:
    return sorted({str(value).strip() for value in (values or []) if str(value).strip()})


def validate_external_plan_constraint_set(
    raw_output: dict[str, Any],
    *,
    expected_objective_numbers: list[str] | None = None,
) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = ExternalPlanConstraintSet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q6_external_instructor_validation_failed:{exc}") from exc
    payload = validated.model_dump(mode="json")
    expected = _normalize_expected_objective_numbers(expected_objective_numbers)
    if expected:
        actual = _normalize_expected_objective_numbers(
            [
                str(item.get("objective_number") or "")
                for item in payload["objective_constraints"]
                if isinstance(item, dict)
            ]
        )
        if actual != expected:
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            raise RuntimeError(
                "q6_external_instructor_validation_failed:"
                f"objective_number_coverage_mismatch:missing={missing}:extra={extra}"
            )
    return payload


def _prompt_with_validation_feedback(*, prompt: str, error_message: str, attempt: int) -> str:
    return f"""{prompt}

--------------------------------------------------------------------------------
【上一轮 Q6 external JSON 未通过 Instructor/Pydantic 合约】
这是第 {attempt} 次重新生成。必须重新输出完整 JSON，不要只输出补丁，不要解释。

错误：
{error_message}

必须修正：
- 每个 objective_constraints[] 对象下，consequence_and_cost、execution_safeguards、verification_contracts、halt_conditions、rationality_assessment 必须互为兄弟字段。
- 只能输出一个 objective_constraints 数组，禁止重复输出 objective_constraints 字段。
- objective_constraints 必须覆盖每一个 Q5_AllowedExternalObjectives_WithConditions 的 objective_number。
- 每个 objective_number 只能出现一次，禁止遗漏、改写或新增 Q5 没有给出的编号。
- 禁止把 execution_safeguards、verification_contracts、halt_conditions、source_compliance_condition 或 rationality_assessment 塞进 consequence_and_cost。
- consequence_and_cost 只能包含 physical_side_effects、blast_radius、data_exposure_risk、file_or_remote_mutation_risk、monetary_cost、compute_cost、latency_cost、rollback_difficulty。
- 所有 required 字段必须出现，禁止多余字段。
"""


def generate_external_plan_constraint_set_with_instructor_contract(
    provider: Any,
    *,
    prompt: str,
    context: dict[str, Any],
    caller_context: Any,
    metadata: dict[str, Any] | None = None,
    expected_objective_numbers: list[str] | None = None,
) -> dict[str, Any]:
    _require_instructor_runtime()
    last_error: RuntimeError | None = None
    attempt_prompt = prompt
    for attempt in range(1, Q6_EXTERNAL_INSTRUCTOR_MAX_ATTEMPTS + 1):
        raw_output = provider.generate_json(
            prompt=attempt_prompt,
            context=context,
            caller_context=caller_context,
            metadata={
                **(metadata or {}),
                "instructor_contract": "ExternalPlanConstraintSet",
                "response_model": "ExternalPlanConstraintSet",
                "instructor_validation_attempt": attempt,
                "instructor_validation_max_attempts": Q6_EXTERNAL_INSTRUCTOR_MAX_ATTEMPTS,
            },
        )
        try:
            return validate_external_plan_constraint_set(
                raw_output,
                expected_objective_numbers=expected_objective_numbers,
            )
        except RuntimeError as exc:
            last_error = exc
            if attempt >= Q6_EXTERNAL_INSTRUCTOR_MAX_ATTEMPTS:
                raise
            attempt_prompt = _prompt_with_validation_feedback(
                prompt=prompt,
                error_message=str(exc),
                attempt=attempt + 1,
            )
    if last_error is not None:
        raise last_error
    raise RuntimeError("q6_external_instructor_validation_failed:retry_exhausted")
