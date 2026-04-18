"""
Q7 (我还可以做什么) evidence extraction.

Contains functions for building and extracting EVIDENCE_Q7 evidence.
"""

import logging
from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q7PreprocessedEvidence,
    Q7AlternativeStrategyInferenceView,
)

from .helpers import _coerce_string_list

logger = logging.getLogger(__name__)


def _extract_q7_preprocessed_evidence(context_payload: object) -> Q7PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    q4 = context_payload.get("q4_capability_boundary_profile") or {}
    q5 = context_payload.get("q5_authorization_boundary_profile") or context_payload.get("q5_permission_boundary") or {}
    q6 = context_payload.get("q6_forbidden_zone_profile") or {}
    q3 = context_payload.get("q3_resource_evaluation") or {}
    q7_baseline = context_payload.get("q7_alternative_strategy_baseline") or {}
    if not q4 and not q5 and not q6:
        logger.error(
            "Q7 evidence extraction: upstream Q4/Q5/Q6 data unavailable — "
            "q4_capability_boundary_profile=%s, q5_authorization_boundary_profile=%s, q6_forbidden_zone_profile=%s. "
            "Q7 无法生成替代策略证据，请检查 Q4/Q5/Q6 执行结果。",
            bool(q4), bool(q5), bool(q6),
        )
        return None

    resource_bottlenecks = _coerce_string_list(
        context_payload.get("q7_resource_bottlenecks")
        or q3.get("missing_critical_assets")
        or q3.get("bottleneck_node")
        or []
    )
    capability_limits = _coerce_string_list(
        context_payload.get("q7_capability_limits")
        or q4.get("capability_upper_limits")
        or []
    )
    permission_boundaries = _coerce_string_list(
        context_payload.get("q7_permission_boundaries")
        or q5.get("allowed_action_space")
        or q5.get("allowed_actions")
        or []
    )
    absolute_red_lines = _coerce_string_list(
        context_payload.get("q7_absolute_red_lines")
        or q6.get("absolute_red_lines")
        or []
    )
    historical_failure_patches = _coerce_string_list(
        q7_baseline.get("fallback_plans")
    )

    return Q7PreprocessedEvidence(
        resource_bottlenecks=resource_bottlenecks,
        capability_limits=capability_limits,
        permission_boundaries=permission_boundaries,
        absolute_red_lines=absolute_red_lines,
        historical_failure_patches=historical_failure_patches,
    )


def _extract_q7_inference_result(result_payload: object) -> Q7AlternativeStrategyInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    profile_raw = result_payload.get("q7_alternative_strategy_profile") or result_payload.get("alternative_strategy_profile") or result_payload
    if not any(
        key in profile_raw
        for key in ("fallback_plans", "degradation_strategies", "collaboration_switches", "exploratory_actions")
    ):
        logger.error(
            "Q7 inference result extraction: alternative strategy profile missing expected keys "
            "(fallback_plans / degradation_strategies / collaboration_switches / exploratory_actions). "
            "插件可能未返回有效策略，结果将显示为空。result_payload keys: %s",
            list(result_payload.keys()) if isinstance(result_payload, dict) else "non-dict",
        )
        return None
    return Q7AlternativeStrategyInferenceView(
        fallback_plans=_coerce_string_list(profile_raw.get("fallback_plans")),
        degradation_strategies=_coerce_string_list(profile_raw.get("degradation_strategies")),
        collaboration_switches=_coerce_string_list(profile_raw.get("collaboration_switches")),
        exploratory_actions=_coerce_string_list(profile_raw.get("exploratory_actions")),
    )


