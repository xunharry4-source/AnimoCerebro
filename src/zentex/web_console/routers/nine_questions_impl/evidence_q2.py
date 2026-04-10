"""
Q2 (我是谁) evidence building and extraction.

Contains functions for building Q2 preprocessed evidence from context snapshots
and extracting Q2 inference results from tool outputs.
"""

from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q2PreprocessedEvidence,
    Q2WhoAmIInferenceView,
    Q2Q1Summary,
    Q2IdentityKernel,
    Q2ManualIntervention,
    Q2RoleView,
    Q2MissionBoundaryView,
)

from .helpers import _coerce_string_list, _humanize_constraint_text


def _has_material_q2_q1_summary(evidence: object) -> bool:
    """Check if Q2 evidence has material Q1 summary."""
    if not isinstance(evidence, dict):
        return False
    q1_summary = evidence.get("q1_summary")
    if not isinstance(q1_summary, dict):
        return False
    primary_domain = str(q1_summary.get("primary_domain") or "").strip().lower()
    secondary_domains = _coerce_string_list(q1_summary.get("secondary_domains"))
    uncertainties = _coerce_string_list(q1_summary.get("uncertainties"))
    risk_summary = str(q1_summary.get("risk_summary") or "").strip()
    return bool(
        (primary_domain and primary_domain != "unknown")
        or secondary_domains
        or uncertainties
        or risk_summary
    )


def _build_q2_preprocessed_evidence(context_payload: dict[str, Any]) -> Q2PreprocessedEvidence | None:
    """Build Q2 preprocessed evidence from context payload."""
    q1_inference = context_payload.get("workspace_domain_inference", {})
    q1_scene_model = context_payload.get("q1_scene_model", {})
    q1_uncertainty_profile = context_payload.get("q1_uncertainty_profile", {})
    if not isinstance(q1_inference, dict):
        q1_inference = {}
    if not isinstance(q1_scene_model, dict):
        q1_scene_model = {}
    if not isinstance(q1_uncertainty_profile, dict):
        q1_uncertainty_profile = {}

    q1_summary = Q2Q1Summary(
        primary_domain=str(
            q1_inference.get("primary_domain")
            or q1_scene_model.get("primary_domain")
            or "unknown"
        ),
        secondary_domains=(
            _coerce_string_list(q1_inference.get("secondary_domains"))
            or _coerce_string_list(q1_scene_model.get("secondary_domains"))
        ),
        uncertainties=(
            _coerce_string_list(q1_inference.get("uncertainties"))
            or _coerce_string_list(q1_uncertainty_profile.get("risk_sources"))
        ),
        risk_summary=(
            str(q1_inference.get("reasoning_summary") or "").strip()
            or str(q1_uncertainty_profile.get("risk_summary") or "").strip()
            or ", ".join(_coerce_string_list(q1_uncertainty_profile.get("risk_sources")))
            or None
        ),
    )

    identity_kernel_raw = (
        context_payload.get("identity_core")
        or context_payload.get("identity_kernel_snapshot")
        or {}
    )
    if not isinstance(identity_kernel_raw, dict):
        identity_kernel_raw = {}

    meta_motivation = identity_kernel_raw.get("meta_motivation")
    if not meta_motivation:
        meta_motivation = " / ".join(_coerce_string_list(identity_kernel_raw.get("meta_drives")))
    values_prohibition = identity_kernel_raw.get("values_prohibition")
    if not values_prohibition:
        values_prohibition = " / ".join(_coerce_string_list(identity_kernel_raw.get("value_vetoes")))

    identity_kernel = Q2IdentityKernel(
        meta_motivation=str(meta_motivation or "No meta-motivation defined."),
        values_prohibition=str(values_prohibition or "No value prohibitions defined."),
        non_bypassable_constraints=[
            text
            for item in _coerce_string_list(identity_kernel_raw.get("non_bypassable_constraints"))
            if (text := _humanize_constraint_text(item))
        ],
    )

    manual_raw = context_payload.get("manual_role_intervention") or context_payload.get("manual_role_overrides") or {}
    manual_intervention = None
    if isinstance(manual_raw, dict) and manual_raw:
        latest_manual = (
            manual_raw.get("reason")
            or manual_raw.get("role_update")
            or manual_raw.get("active_role_override")
            or "manual override"
        )
        applied_at = manual_raw.get("timestamp") or manual_raw.get("applied_at")
        manual_intervention = Q2ManualIntervention(
            latest_manual_role_modification=str(latest_manual),
            applied_at=str(applied_at) if applied_at else None,
        )

    return Q2PreprocessedEvidence(
        q1_summary=q1_summary,
        identity_kernel=identity_kernel,
        manual_intervention=manual_intervention,
    )


def _extract_q2_preprocessed_evidence(context_payload: object) -> Q2PreprocessedEvidence | None:
    """Extract Q2 preprocessed evidence from context payload if available."""
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in (
            "identity_core",
            "identity_kernel_snapshot",
            "workspace_domain_inference",
            "q1_scene_model",
            "q1_uncertainty_profile",
            "manual_role_intervention",
            "manual_role_overrides",
        )
    ):
        return None
    return _build_q2_preprocessed_evidence(context_payload)


def _extract_q2_inference_result(result_payload: object) -> Q2WhoAmIInferenceView | None:
    """Extract Q2 inference result from tool output payload."""
    if not isinstance(result_payload, dict):
        return None

    role_profile_raw = result_payload.get("role_profile")
    mission_boundary_raw = result_payload.get("mission_boundary")

    if not isinstance(role_profile_raw, dict) or not isinstance(mission_boundary_raw, dict):
        return None

    return Q2WhoAmIInferenceView(
        role_profile=Q2RoleView(
            identity_role=str(role_profile_raw.get("identity_role") or ""),
            active_role=str(role_profile_raw.get("active_role") or ""),
            task_role=str(role_profile_raw.get("task_role") or ""),
        ),
        mission_boundary=Q2MissionBoundaryView(
            current_mission=str(mission_boundary_raw.get("current_mission") or ""),
            priority_duties=_coerce_string_list(mission_boundary_raw.get("priority_duties")),
            continuity_boundaries=_coerce_string_list(mission_boundary_raw.get("continuity_boundaries")),
        ),
    )
