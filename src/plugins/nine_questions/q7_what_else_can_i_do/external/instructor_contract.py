from __future__ import annotations

import logging
from typing import Any, List, Literal
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q7_external_instructor_not_installed") from exc


class ExternalCreativePossibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_number: str = Field(min_length=1)
    possibility_type: Literal[
        "public_competitor_signal_research",
        "content_quality_opportunities",
        "subreddit_rule_learning",
        "authorized_account_compliance_audit",
        "unregistered_agent_options",
        "unknown_cli_options",
        "new_mcp_server_options",
        "new_connector_options",
        "browser_or_saas_automation_options",
        "external_service_options",
        "collaboration_opportunities",
        "tool_learning_opportunities",
        "low_risk_probe_candidates",
    ]
    possibility_description: str = Field(min_length=1)
    possibility_status: Literal[
        "hypothetical",
        "needs_discovery",
        "needs_learning",
        "needs_registration",
        "needs_verification",
        "needs_authorization",
        "ready_for_q4_objective_candidate",
    ]
    divergent_rationale: str = Field(min_length=1)


class ExternalCreativePossibilitySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ExternalCreativePossibilitySet"]
    creative_possibilities: List[ExternalCreativePossibility] = Field(min_length=3)

    @model_validator(mode="after")
    def check_distinct_types(self) -> Self:
        types = {p.possibility_type for p in self.creative_possibilities}
        if len(types) < 3:
            raise ValueError("q7_external_creative_possibilities_distinct_type_minimum_3_required")
        return self


def validate_external_creative_possibility_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = ExternalCreativePossibilitySet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q7_external_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_external_creative_possibility_set_with_instructor_contract(
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
            "instructor_contract": "ExternalCreativePossibilitySet",
            "response_model": "ExternalCreativePossibilitySet",
        },
    )
    return validate_external_creative_possibility_set(raw_output)
