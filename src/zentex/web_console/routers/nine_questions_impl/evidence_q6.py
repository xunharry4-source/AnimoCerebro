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
    # 读取实际写入的 key
    q4 = context_payload.get("q4_capability_boundary_profile") or {}
    q5 = context_payload.get("q5_permission_boundary") or context_payload.get("q5_authorization_boundary_profile") or {}
    q6_baseline = context_payload.get("q6_forbidden_zone_baseline") or {}
    q6_profile = context_payload.get("q6_forbidden_zone_profile") or {}
    if not q4 and not q5 and not q6_baseline and not q6_profile:
        return None
    # 从 Q4 提取 actionable_space
    actionable = q4.get("actionable_space") or q4.get("capability_upper_limits") or []
    # 从 Q5 提取 authorization_boundaries
    auth = q5.get("allowed_action_space") or q5.get("allowed_actions") or []
    # 从 Q5 提取 forbidden
    forbidden = q5.get("forbidden_action_space") or []
    if not forbidden and isinstance(q6_baseline, dict):
        forbidden = q6_baseline.get("absolute_red_lines") or []
    if not forbidden and isinstance(q6_profile, dict):
        forbidden = q6_profile.get("absolute_red_lines") or q6_profile.get("prohibited_strategies") or []
    historical_strategy_patches = []
    if isinstance(q6_baseline, dict):
        historical_strategy_patches = _coerce_string_list(q6_baseline.get("prohibited_strategies"))
    if not historical_strategy_patches and isinstance(q6_profile, dict):
        historical_strategy_patches = _coerce_string_list(q6_profile.get("prohibited_strategies"))
    return Q6PreprocessedEvidence(
        actionable_space=_coerce_string_list(actionable),
        authorization_boundaries=_coerce_string_list(auth),
        non_bypassable_constraints=_coerce_string_list(forbidden),
        historical_strategy_patches=historical_strategy_patches,
    )


def _extract_q6_inference_result(result_payload: object) -> Q6ForbiddenZoneInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    source_payload = (
        result_payload.get("forbidden_zone_profile")
        or result_payload.get("q6_forbidden_zone_profile")
    )
    source_payload = source_payload if isinstance(source_payload, dict) else result_payload
    if not any(
        key in source_payload
        for key in ("absolute_red_lines", "performance_tradeoff_bans", "prohibited_strategies", "contamination_risks")
    ):
        return None
    return Q6ForbiddenZoneInferenceView(
        absolute_red_lines=_coerce_string_list(source_payload.get("absolute_red_lines")),
        performance_tradeoff_bans=_coerce_string_list(source_payload.get("performance_tradeoff_bans")),
        prohibited_strategies=_coerce_string_list(source_payload.get("prohibited_strategies")),
        contamination_risks=_coerce_string_list(source_payload.get("contamination_risks")),
    )
