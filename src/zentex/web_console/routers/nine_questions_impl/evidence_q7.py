from __future__ import annotations

"""
Q7 (我还可以做什么) evidence extraction.

Contains functions for building and extracting EVIDENCE_Q7 evidence.
"""

from typing import Any, Dict, List, Optional, Union

from zentex.web_console.contracts.nine_questions import (
    Q7PreprocessedEvidence,
    Q7AlternativeStrategyInferenceView,
)

from .helpers import _coerce_string_list


def _unwrap_red_line_assessment(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    wrapped = payload.get("RedLineAssessment")
    if isinstance(wrapped, dict):
        return wrapped
    return payload


def _extract_q7_preprocessed_evidence(context_payload: object) -> Optional[Q7PreprocessedEvidence]:
    if not isinstance(context_payload, dict):
        return None
    q5 = context_payload.get("q5_authorization_boundary_profile") or context_payload.get("q5_permission_boundary") or {}
    q7_baseline = context_payload.get("q7_red_line_baseline") or {}
    q7_assessment = _unwrap_red_line_assessment(
        context_payload.get("q7_red_line_assessment")
        or context_payload.get("red_line_assessment")
        or context_payload.get("RedLineAssessment")
        or {}
    )
    if not q7_baseline and not q7_assessment and not q5:
        return None

    return Q7PreprocessedEvidence(
        identity_kernel_constraints=_coerce_string_list(
            q7_baseline.get("identity_kernel_constraints")
            or context_payload.get("identity_kernel_constraints")
            or []
        ),
        authorization_boundary_constraints=_coerce_string_list(
            q7_baseline.get("authorization_boundary_constraints")
            or q5.get("forbidden_action_space")
            or q5.get("unauthorized_actions")
            or []
        ),
        safety_rejection_history=_coerce_string_list(
            q7_baseline.get("safety_rejection_history")
            or context_payload.get("q7_rejected_operation_records")
            or []
        ),
        procedural_memory_constraints=_coerce_string_list(
            q7_baseline.get("procedural_memory_constraints")
            or context_payload.get("procedural_memory_constraints")
            or []
        ),
        non_bypassable_constraints=_coerce_string_list(
            q7_assessment.get("non_bypassable_constraints")
            or q7_baseline.get("non_bypassable_constraints")
            or context_payload.get("q7_non_bypassable_constraints")
            or []
        ),
        ban_source_explanations=_coerce_string_list(
            q7_assessment.get("ban_source_explanations")
            or q7_assessment.get("constraint_sources_explanation")
            or q7_baseline.get("ban_source_explanations")
            or context_payload.get("q7_ban_source_explanations")
            or context_payload.get("q7_constraint_sources_explanation")
            or []
        ),
        question_driver_refs=_coerce_string_list(
            q7_assessment.get("question_driver_refs")
            or q7_baseline.get("question_driver_refs")
            or context_payload.get("q7_question_driver_refs")
            or []
        ),
    )


def _extract_q7_inference_result(result_payload: object) -> Optional[Q7AlternativeStrategyInferenceView]:
    if not isinstance(result_payload, dict):
        return None
    profile_raw = _unwrap_red_line_assessment(
        result_payload.get("q7_red_line_assessment")
        or result_payload.get("red_line_assessment")
        or result_payload.get("RedLineAssessment")
        or result_payload
    )
    if not any(
        key in profile_raw
        for key in (
            "current_red_line_hits",
            "current_redline_hits",
            "rejected_operation_records",
            "rejected_operations_log",
            "ban_source_explanations",
            "constraint_sources_explanation",
            "non_bypassable_constraints",
            "question_driver_refs",
        )
    ):
        return None
    return Q7AlternativeStrategyInferenceView(
        current_red_line_hits=_coerce_string_list(profile_raw.get("current_red_line_hits") or profile_raw.get("current_redline_hits")),
        rejected_operation_records=_coerce_string_list(profile_raw.get("rejected_operation_records") or profile_raw.get("rejected_operations_log")),
        ban_source_explanations=_coerce_string_list(profile_raw.get("ban_source_explanations") or profile_raw.get("constraint_sources_explanation")),
        non_bypassable_constraints=_coerce_string_list(profile_raw.get("non_bypassable_constraints")),
        question_driver_refs=_coerce_string_list(profile_raw.get("question_driver_refs")),
    )
