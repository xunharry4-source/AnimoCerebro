"""
Q4 (我能做什么) evidence extraction.

Contains functions for building and extracting EVIDENCE_Q4 evidence.
"""

from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q4PreprocessedEvidence,
    Q4WhatCanIDoInferenceView,
)

from .helpers import _coerce_string_list


def _extract_q4_preprocessed_evidence(context_payload: object) -> Q4PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None
    permission_profile = context_payload.get("q4_permission_profile")
    permission_profile = permission_profile if isinstance(permission_profile, dict) else {}
    active_execution_domains = _coerce_string_list(context_payload.get("q4_active_execution_domains"))
    capability_baseline = context_payload.get("q4_capability_baseline")
    capability_baseline = capability_baseline if isinstance(capability_baseline, dict) else {}

    q1_context = {
        "scene_model": context_payload.get("q1_scene_model") if isinstance(context_payload.get("q1_scene_model"), dict) else {},
        "uncertainty_profile": context_payload.get("q1_uncertainty_profile")
        if isinstance(context_payload.get("q1_uncertainty_profile"), dict)
        else {},
    }
    q2_context = {
        "role_profile": context_payload.get("q2_role_profile") if isinstance(context_payload.get("q2_role_profile"), dict) else {},
        "mission_boundary": context_payload.get("q2_mission_boundary")
        if isinstance(context_payload.get("q2_mission_boundary"), dict)
        else {},
    }
    q3_inventory = {
        "available_cognitive_tools": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("available_cognitive_tools")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "available_execution_tools": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("available_execution_tools")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "connected_agents": (
            (context_payload.get("q3_unified_asset_inventory") or {}).get("connected_agents")
            if isinstance((context_payload.get("q3_unified_asset_inventory") or {}).get("connected_agents"), list)
            else []
        ),
        "activated_strategy_patches": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("activated_strategy_patches")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "accessible_workspace_zones": _coerce_string_list(
            (context_payload.get("q3_unified_asset_inventory") or {}).get("accessible_workspace_zones")
            if isinstance(context_payload.get("q3_unified_asset_inventory"), dict)
            else None
        ),
        "permission_profile": permission_profile,
        "active_execution_domains": active_execution_domains,
        "capability_baseline": capability_baseline,
        "resource_evaluation": context_payload.get("q3_resource_evaluation")
        if isinstance(context_payload.get("q3_resource_evaluation"), dict)
        else {},
    }
    if not any(
        (
            q1_context["scene_model"],
            q1_context["uncertainty_profile"],
            q2_context["role_profile"],
            q2_context["mission_boundary"],
            q3_inventory["available_cognitive_tools"],
            q3_inventory["available_execution_tools"],
            q3_inventory["connected_agents"],
            q3_inventory["activated_strategy_patches"],
            q3_inventory["accessible_workspace_zones"],
            q3_inventory["permission_profile"],
            q3_inventory["active_execution_domains"],
            q3_inventory["capability_baseline"],
            q3_inventory["resource_evaluation"],
        )
    ):
        return None
    return Q4PreprocessedEvidence(q1_context=q1_context, q2_context=q2_context, q3_inventory=q3_inventory)


def _extract_q4_inference_result(result_payload: object) -> Q4WhatCanIDoInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    payload = (
        result_payload.get("capability_boundary_profile")
        if isinstance(result_payload.get("capability_boundary_profile"), dict)
        else result_payload.get("q4_capability_boundary_profile")
        if isinstance(result_payload.get("q4_capability_boundary_profile"), dict)
        else result_payload
    )
    if not isinstance(payload, dict) or not any(
        key in payload for key in ("capability_upper_limits", "actionable_space", "executable_strategies")
    ):
        return None
    return Q4WhatCanIDoInferenceView(
        capability_upper_limits=_coerce_string_list(payload.get("capability_upper_limits")),
        actionable_space=_coerce_string_list(payload.get("actionable_space")),
        executable_strategies=_coerce_string_list(payload.get("executable_strategies")),
    )


