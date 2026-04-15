from __future__ import annotations

"""
Q1 integration for the LLM upgrade system.

This file builds Q1-specific upgrade requests and optional candidate plans so
Q1 can participate in the new DSPy upgrade flow without forcing the main
inference path to fail when upgrade planning is not configured.
"""

from typing import Any

from plugins.nine_questions.q1_where_am_i.models import WorkspaceDomainInference
from plugins.nine_questions.q1_where_am_i.upgrade_models import (
    Q1LLMUpgradePlanPayload,
    Q1LLMUpgradeProfile,
)
from pydantic import BaseModel, ConfigDict, Field


class LLMUpgradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    program_id: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    target_metric: str = Field(min_length=1)
    dataset_refs: list[str] = Field(default_factory=list)
    objective_summary: str = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)


Q1_PROGRAM_ID = "nine_questions.q1.where_am_i"
Q1_TARGET_COMPONENT = "workspace_domain_inference"
Q1_TARGET_METRIC = "q1_domain_accuracy"


def _build_objective_summary(inference: WorkspaceDomainInference) -> str:
    uncertainty_count = len(inference.uncertainties)
    return (
        "Improve Q1 workspace-domain inference stability and reduce ambiguity "
        f"for primary domain '{inference.primary_domain}' with {uncertainty_count} "
        "observed uncertainty signals."
    )


def build_q1_upgrade_profile(
    *,
    baseline_version: str,
    inference: WorkspaceDomainInference,
) -> Q1LLMUpgradeProfile:
    """Build the default Q1 upgrade profile from the current inference result."""

    return Q1LLMUpgradeProfile(
        program_id=Q1_PROGRAM_ID,
        target_component=Q1_TARGET_COMPONENT,
        baseline_version=baseline_version,
        target_metric=Q1_TARGET_METRIC,
        objective_summary=_build_objective_summary(inference),
        dataset_refs=[
            "tests/plugins/test_q1_where_am_i_plugin.py",
            "tests/web_console/api/test_q1_production_evidence.py",
        ],
        validation_commands=[
            "pytest tests/plugins/test_q1_where_am_i_plugin.py -q",
            "pytest tests/web_console/api/test_q1_production_evidence.py -q",
        ],
    )


def build_q1_upgrade_request(
    *,
    baseline_version: str,
    inference: WorkspaceDomainInference,
) -> LLMUpgradeRequest:
    """Translate the Q1 upgrade profile into the generic LLM upgrade contract."""

    profile = build_q1_upgrade_profile(
        baseline_version=baseline_version,
        inference=inference,
    )
    return LLMUpgradeRequest(
        program_id=profile.program_id,
        target_component=profile.target_component,
        baseline_version=profile.baseline_version,
        target_metric=profile.target_metric,
        dataset_refs=profile.dataset_refs,
        objective_summary=profile.objective_summary,
        validation_commands=profile.validation_commands,
    )


def build_q1_upgrade_payload(
    *,
    baseline_version: str,
    inference: WorkspaceDomainInference,
    upgrade_service: Any = None,
    enable_candidate_planning: bool = False,
) -> Q1LLMUpgradePlanPayload:
    """
    Build Q1 upgrade metadata with optional candidate planning.

    Fail-open for the optional planning path:
    - Q1 inference itself must not break just because DSPy planning is absent
    - when planning is enabled and a planner fails, the failure is surfaced in
      the payload instead of being silently swallowed
    """

    profile = build_q1_upgrade_profile(
        baseline_version=baseline_version,
        inference=inference,
    )
    if not enable_candidate_planning or upgrade_service is None:
        return Q1LLMUpgradePlanPayload(
            planning_status="profile_only",
            profile=profile,
        )

    if not callable(getattr(upgrade_service, "plan_candidate", None)):
        return Q1LLMUpgradePlanPayload(
            planning_status="planning_failed",
            profile=profile,
            error_message="llm_upgrade_service must expose plan_candidate(request)",
        )

    request = build_q1_upgrade_request(
        baseline_version=baseline_version,
        inference=inference,
    )
    try:
        candidate = upgrade_service.plan_candidate(request)
    except Exception as exc:
        return Q1LLMUpgradePlanPayload(
            planning_status="planning_failed",
            profile=profile,
            error_message=str(exc),
        )

    return Q1LLMUpgradePlanPayload(
        planning_status="candidate_planned",
        profile=profile,
        candidate_version=candidate.candidate_version,
        release_gate=list(candidate.release_gate),
    )
