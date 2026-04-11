"""
Q6 (我即使能做也不该做什么) evidence extraction.

Contains functions for building and extracting EVIDENCE_Q6 evidence.
"""

from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q6PreprocessedEvidence,
    Q6ForbiddenZoneInferenceView,
)

from .helpers import _coerce_string_list


def _extract_q6_preprocessed_evidence(context_payload: object) -> Q6PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in ("actionable_space", "authorization_boundaries", "non_bypassable_constraints", "historical_strategy_patches")
    ):
        return None
    return Q6PreprocessedEvidence(
        actionable_space=_coerce_string_list(context_payload.get("actionable_space")),
        authorization_boundaries=_coerce_string_list(context_payload.get("authorization_boundaries")),
        non_bypassable_constraints=_coerce_string_list(context_payload.get("non_bypassable_constraints")),
        historical_strategy_patches=_coerce_string_list(context_payload.get("historical_strategy_patches")),
    )


def _extract_q6_inference_result(result_payload: object) -> Q6ForbiddenZoneInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    if not any(
        key in result_payload
        for key in ("absolute_red_lines", "performance_tradeoff_bans", "prohibited_strategies", "contamination_risks")
    ):
        return None
    return Q6ForbiddenZoneInferenceView(
        absolute_red_lines=_coerce_string_list(result_payload.get("absolute_red_lines")),
        performance_tradeoff_bans=_coerce_string_list(result_payload.get("performance_tradeoff_bans")),
        prohibited_strategies=_coerce_string_list(result_payload.get("prohibited_strategies")),
        contamination_risks=_coerce_string_list(result_payload.get("contamination_risks")),
    )



