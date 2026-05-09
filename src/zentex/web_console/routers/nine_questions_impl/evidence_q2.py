from __future__ import annotations

"""
Q2 (我有什么) evidence building and extraction.

Contains functions for building Q2 preprocessed evidence from context snapshots
and extracting Q2 inference results from tool outputs.
"""

import json
from typing import Any, Dict, List, Optional, Union

from zentex.web_console.contracts.nine_questions import (
    Q2PreprocessedEvidence,
    Q2WhoAmIInferenceView,
    Q2Q1Summary,
    Q2IdentityKernel,
    Q2ManualIntervention,
    Q2RoleView,
    Q2RoleAlignmentJudgementView,
    Q2MissionBoundaryView,
)

from .helpers import _coerce_string_list, _humanize_constraint_text


def _identity_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text and text[0] in {"{", "["}:
            try:
                return _identity_text(json.loads(text))
            except Exception:
                return text
        return text
    if isinstance(value, (list, tuple)):
        return " / ".join(item for raw in value if (item := _identity_text(raw)))
    if isinstance(value, dict):
        preferred_keys = (
            "summary",
            "description",
            "motivation",
            "value",
            "rule",
            "constraint",
            "reason",
            "intent",
            "name",
            "title",
        )
        preferred_values = [_identity_text(value.get(key)) for key in preferred_keys if key in value]
        remaining_values = [
            f"{key}: {text}"
            for key, raw in value.items()
            if key not in preferred_keys and (text := _identity_text(raw))
        ]
        return "；".join(item for item in preferred_values + remaining_values if item)
    return str(value).strip()


def _identity_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _identity_text(item))]
    text = _identity_text(value)
    return [text] if text else []


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


def _build_q2_preprocessed_evidence(context_payload: dict[str, Any]) -> Optional[Q2PreprocessedEvidence]:
    """Build Q2 preprocessed evidence from context payload."""
    asset_inventory = context_payload.get("q2_asset_inventory") or context_payload.get("asset_inventory") or {}
    unified_inventory = context_payload.get("q2_unified_asset_inventory") or {}
    humanized_inventory = context_payload.get("q2_humanized_asset_inventory") or {}
    if isinstance(asset_inventory, dict) and (
        asset_inventory or isinstance(unified_inventory, dict) and unified_inventory
    ):
        return Q2PreprocessedEvidence(
            workspace_permission=context_payload.get("workspaces_and_permissions")
            if isinstance(context_payload.get("workspaces_and_permissions"), dict)
            else {},
            tools_agents={
                "unified_inventory": unified_inventory if isinstance(unified_inventory, dict) else {},
                "humanized_inventory": humanized_inventory if isinstance(humanized_inventory, dict) else {},
            },
            memory_strategy=context_payload.get("memory_and_strategy")
            if isinstance(context_payload.get("memory_and_strategy"), dict)
            else {},
            asset_inventory=asset_inventory,
        )

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
        meta_motivation = _identity_text(
            identity_kernel_raw.get("meta_drives")
            or identity_kernel_raw.get("meta_motivations")
            or identity_kernel_raw.get("motivation")
        )
    values_prohibition = identity_kernel_raw.get("values_prohibition")
    if not values_prohibition:
        values_prohibition = _identity_text(
            identity_kernel_raw.get("value_vetoes")
            or identity_kernel_raw.get("values_prohibitions")
            or identity_kernel_raw.get("core_value_prohibitions")
            or identity_kernel_raw.get("prohibitions")
        )

    identity_kernel = Q2IdentityKernel(
        meta_motivation=_identity_text(meta_motivation) or "No meta-motivation defined.",
        values_prohibition=_identity_text(values_prohibition) or "No value prohibitions defined.",
        non_bypassable_constraints=[
            text
            for item in _identity_text_list(identity_kernel_raw.get("non_bypassable_constraints"))
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


def _extract_q2_preprocessed_evidence(context_payload: object) -> Optional[Q2PreprocessedEvidence]:
    """Extract Q2 preprocessed evidence from context payload if available."""
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in (
            "q2_asset_inventory",
            "asset_inventory",
            "q2_unified_asset_inventory",
            "q2_humanized_asset_inventory",
            "workspaces_and_permissions",
            "memory_and_strategy",
        )
    ):
        return None
    return _build_q2_preprocessed_evidence(context_payload)


def _extract_q2_inference_result(result_payload: object) -> Optional[Q2WhoAmIInferenceView]:
    """Extract Q2 inference result from tool output payload."""
    if not isinstance(result_payload, dict):
        return None

    asset_inventory = result_payload.get("q2_asset_inventory") or result_payload.get("asset_inventory")
    if not isinstance(asset_inventory, dict):
        asset_inventory = {
            key: result_payload.get(key)
            for key in (
                "long_term_memory",
                "cognitive_and_functional_tools",
                "connected_agents",
                "strategy_patches",
                "inventory_summary",
            )
            if key in result_payload
        }
    context_updates = result_payload.get("context_updates") if isinstance(result_payload.get("context_updates"), dict) else {}
    if not asset_inventory and isinstance(context_updates, dict):
        asset_inventory = context_updates.get("q2_asset_inventory") or context_updates.get("asset_inventory")
    if isinstance(asset_inventory, dict) and asset_inventory:
        sufficiency_raw = (
            result_payload.get("sufficiency_assessment")
            or result_payload.get("resource_evaluation")
            or result_payload.get("q2_resource_evaluation")
            or (context_updates.get("q2_resource_evaluation") if isinstance(context_updates, dict) else None)
        )
        if not isinstance(sufficiency_raw, dict):
            return None
        return Q2WhoAmIInferenceView(
            asset_inventory=asset_inventory,
            sufficiency_assessment={
                "resource_status": str(sufficiency_raw.get("resource_status") or "unknown"),
                "missing_critical_assets": _coerce_string_list(sufficiency_raw.get("missing_critical_assets")),
                "bottleneck_node": sufficiency_raw.get("bottleneck_node"),
                "reasoning_summary": sufficiency_raw.get("reasoning_summary"),
            },
        )

    return None
