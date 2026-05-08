from __future__ import annotations

import logging
from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q9_internal_instructor_not_installed") from exc


class Q9InternalActionDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_objective: str = Field(min_length=1)
    internal_steps: List[str] = Field(min_length=1)
    required_internal_resources: List[str] = Field(min_length=1)
    verification_checks: List[str] = Field(min_length=1)
    stop_conditions: List[str] = Field(min_length=1)
    evidence_refs: List[str] = Field(min_length=1)


class Q9InternalActionDesignRoot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Q9InternalActionDesign: Q9InternalActionDesign


def validate_internal_action_design(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = Q9InternalActionDesignRoot.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q9_internal_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")["Q9InternalActionDesign"]


def generate_internal_action_design_with_instructor_contract(
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
            "instructor_contract": "Q9InternalActionDesignRoot",
            "response_model": "Q9InternalActionDesignRoot",
        },
    )
    return validate_internal_action_design(raw_output)
