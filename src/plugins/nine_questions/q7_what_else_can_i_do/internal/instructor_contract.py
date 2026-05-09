from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q7_internal_instructor_not_installed") from exc


class InternalCreativePossibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_number: str = Field(min_length=1)
    category: Literal[
        "alternative_internal_objectives",
        "new_reasoning_paths",
        "new_reflection_methods",
        "new_memory_architecture_options",
        "value_prompting_possibilities",
        "learning_opportunities",
        "self_evolution_possibilities",
        "pure_cognitive_plugin_ideas",
        "low_cost_internal_experiments",
    ]
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    possibility_status: Literal[
        "hypothetical",
        "needs_discovery",
        "needs_learning",
        "needs_verification",
        "needs_authorization",
        "ready_for_q4_objective_candidate",
    ]


class InternalCreativePossibilitySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["InternalCreativePossibilitySet"]
    creative_possibilities: List[InternalCreativePossibility] = Field(min_length=1)


def validate_internal_creative_possibility_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = InternalCreativePossibilitySet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q7_internal_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_internal_creative_possibility_set_with_instructor_contract(
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
            "instructor_contract": "InternalCreativePossibilitySet",
            "response_model": "InternalCreativePossibilitySet",
        },
    )
    return validate_internal_creative_possibility_set(raw_output)
