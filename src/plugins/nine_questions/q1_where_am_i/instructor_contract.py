from __future__ import annotations

import logging
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q1_instructor_not_installed") from exc


class WorkspaceDomainInference(BaseModel):
    """
    Strict output contract for Q1 environment inference.

    Hard requirements:
    - Missing any required field is a hard failure (fail-closed).
    - secondary_domains must allow mixed scenarios (code + billing, etc).
    """

    model_config = ConfigDict(extra="forbid")

    primary_domain: str = Field(min_length=1)
    secondary_domains: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = Field(min_length=1)
    uncertainties: List[str] = Field(default_factory=list, min_length=1)
    suggested_first_step: str = Field(min_length=1)
    host_runtime_type: Optional[str] = Field(default=None)
    host_runtime_reason: Optional[str] = Field(default=None)


def validate_workspace_domain_inference(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = WorkspaceDomainInference.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q1_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_workspace_domain_inference_with_instructor_contract(
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
            "instructor_contract": "WorkspaceDomainInference",
            "response_model": "WorkspaceDomainInference",
        },
    )
    return validate_workspace_domain_inference(raw_output)
