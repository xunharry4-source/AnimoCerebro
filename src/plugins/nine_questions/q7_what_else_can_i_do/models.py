from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pydantic.types import StrictStr


class RedLineAssessment(BaseModel):
    """
    Q7 Result: Red-line and constraint assessment.

    This is the strict live-LLM output contract under the RedLineAssessment
    root object; no extra fields are allowed.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_redline_hits: List[StrictStr] = Field(
        default_factory=list,
        description="当前正在触碰或即将触碰的风险红线；无明显违规意图时为空数组。",
    )
    rejected_operations_log: List[StrictStr] = Field(
        default_factory=list,
        description="近期被安全门或审计通道明确拦截的操作记录；无记录时为空数组。",
    )
    constraint_sources_explanation: StrictStr = Field(
        ...,
        min_length=1,
        description="一句话说明禁令来源，例如身份边界、Q5 授权边界、安全门和审计通道。",
    )
    non_bypassable_constraints: List[StrictStr] = Field(
        ...,
        min_length=1,
        description="身份边界与 Q5 Authorization 中的不可绕过约束和禁止操作，全量继承，不得删减。",
    )

    @field_validator(
        "current_redline_hits",
        "rejected_operations_log",
        "non_bypassable_constraints",
    )
    @classmethod
    def reject_blank_items(cls, value: List[StrictStr]) -> List[StrictStr]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Q7 RedLineAssessment arrays cannot contain blank strings")
        return normalized


class Q7InferenceResult(BaseModel):
    """
    Strict LLM output contract for Q7.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    RedLineAssessment: RedLineAssessment
