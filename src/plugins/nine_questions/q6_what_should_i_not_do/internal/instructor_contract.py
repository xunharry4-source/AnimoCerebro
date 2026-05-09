from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)
Q6_INTERNAL_INSTRUCTOR_MAX_ATTEMPTS = 3


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


def _normalize_expected_objective_numbers(values: list[str] | None) -> list[str]:
    return sorted({str(value).strip() for value in (values or []) if str(value).strip()})


def validate_internal_plan_constraint_set(
    raw_output: dict[str, Any],
    *,
    expected_objective_numbers: list[str] | None = None,
) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = InternalPlanConstraintSet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q6_internal_instructor_validation_failed:{exc}") from exc
    payload = validated.model_dump(mode="json")
    expected = _normalize_expected_objective_numbers(expected_objective_numbers)
    if expected:
        actual = _normalize_expected_objective_numbers(
            [
                str(item.get("objective_number") or "")
                for item in payload["constraints_by_objective"]
                if isinstance(item, dict)
            ]
        )
        if actual != expected:
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            raise RuntimeError(
                "q6_internal_instructor_validation_failed:"
                f"objective_number_coverage_mismatch:missing={missing}:extra={extra}"
            )
    return payload


def _prompt_with_validation_feedback(*, prompt: str, error_message: str, attempt: int) -> str:
    return f"""{prompt}

--------------------------------------------------------------------------------
【上一轮 Q6 internal JSON 未通过 Instructor/Pydantic 合约】
这是第 {attempt} 次重新生成。必须重新输出完整 JSON，不要只输出补丁，不要解释。

错误：
{error_message}

必须修正：
- 只能输出一个 constraints_by_objective 数组，禁止重复输出 constraints_by_objective 字段。
- constraints_by_objective 必须覆盖每一个 Q5_AllowedInternalObjectives 的 objective_number。
- 每个 objective_number 只能出现一次，禁止遗漏、改写或新增 Q5 没有给出的编号。
- 所有 required 字段必须出现，禁止多余字段。
"""


def generate_internal_plan_constraint_set_with_instructor_contract(
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
    for attempt in range(1, Q6_INTERNAL_INSTRUCTOR_MAX_ATTEMPTS + 1):
        raw_output = provider.generate_json(
            prompt=attempt_prompt,
            context=context,
            caller_context=caller_context,
            metadata={
                **(metadata or {}),
                "instructor_contract": "InternalPlanConstraintSet",
                "response_model": "InternalPlanConstraintSet",
                "instructor_validation_attempt": attempt,
                "instructor_validation_max_attempts": Q6_INTERNAL_INSTRUCTOR_MAX_ATTEMPTS,
            },
        )
        try:
            return validate_internal_plan_constraint_set(
                raw_output,
                expected_objective_numbers=expected_objective_numbers,
            )
        except RuntimeError as exc:
            last_error = exc
            if attempt >= Q6_INTERNAL_INSTRUCTOR_MAX_ATTEMPTS:
                raise
            attempt_prompt = _prompt_with_validation_feedback(
                prompt=prompt,
                error_message=str(exc),
                attempt=attempt + 1,
            )
    if last_error is not None:
        raise last_error
    raise RuntimeError("q6_internal_instructor_validation_failed:retry_exhausted")
