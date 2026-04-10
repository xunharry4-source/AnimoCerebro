"""
Q7 (我还可以做什么) evidence extraction.

Contains functions for building and extracting EVIDENCE_Q7 evidence.
"""

from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q7PreprocessedEvidence,
    Q7AlternativeStrategyInferenceView,
)

from .helpers import _coerce_string_list


def _extract_q7_preprocessed_evidence(context_payload: object) -> Q7PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in ("resource_bottlenecks", "capability_limits", "permission_boundaries", "absolute_red_lines", "historical_failure_patches")
    ):
        return None
    return Q7PreprocessedEvidence(
        resource_bottlenecks=_coerce_string_list(context_payload.get("resource_bottlenecks")),
        capability_limits=_coerce_string_list(context_payload.get("capability_limits")),
        permission_boundaries=_coerce_string_list(context_payload.get("permission_boundaries")),
        absolute_red_lines=_coerce_string_list(context_payload.get("absolute_red_lines")),
        historical_failure_patches=_coerce_string_list(context_payload.get("historical_failure_patches")),
    )


def _extract_q7_inference_result(result_payload: object) -> Q7AlternativeStrategyInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    if not any(
        key in result_payload
        for key in ("fallback_plans", "degradation_strategies", "collaboration_switches", "exploratory_actions")
    ):
        return None
    return Q7AlternativeStrategyInferenceView(
        fallback_plans=_coerce_string_list(result_payload.get("fallback_plans")),
        degradation_strategies=_coerce_string_list(result_payload.get("degradation_strategies")),
        collaboration_switches=_coerce_string_list(result_payload.get("collaboration_switches")),
        exploratory_actions=_coerce_string_list(result_payload.get("exploratory_actions")),
    )



