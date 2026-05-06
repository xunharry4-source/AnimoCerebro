from __future__ import annotations

from typing import Any


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            if isinstance(item, dict):
                action = normalize_text(item.get("action") or item.get("operation") or item.get("name"))
                reason = normalize_text(item.get("reason") or item.get("source") or item.get("policy"))
                text = f"{action}: {reason}" if action and reason else action or reason
            else:
                text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _meaningful_text_list(*values: object) -> list[str]:
    merged: list[str] = []
    for value in values:
        for item in coerce_string_list(value):
            lowered = item.strip().lower()
            if lowered in {"n/a", "na", "none", "unknown", "null"}:
                continue
            merged.append(item)
    return list(dict.fromkeys(entry for entry in merged if normalize_text(entry)))


def _flatten_identity_kernel_constraints(identity_kernel: dict[str, Any]) -> list[str]:
    if not isinstance(identity_kernel, dict):
        return []
    return _meaningful_text_list(
        identity_kernel.get("non_bypassable_constraints"),
        identity_kernel.get("self_binding_constraints"),
        identity_kernel.get("core_values"),
        identity_kernel.get("value_vetoes"),
        identity_kernel.get("values_prohibition"),
    )


def _q5_red_line_sources(q5_profile: dict[str, Any], q5_permission_boundary: dict[str, Any]) -> list[str]:
    if not isinstance(q5_profile, dict):
        q5_profile = {}
    if not isinstance(q5_permission_boundary, dict):
        q5_permission_boundary = {}
    return _meaningful_text_list(
        q5_profile.get("forbidden_action_space"),
        q5_profile.get("forbidden_actions"),
        q5_profile.get("forbidden_operations"),
        q5_profile.get("requires_escalation_actions"),
        q5_profile.get("compliance_risks"),
        q5_permission_boundary.get("unauthorized_actions"),
        q5_permission_boundary.get("conditional_actions"),
    )


def derive_red_line_assessment_baseline(
    *,
    identity_kernel: dict[str, Any],
    q3_mission_boundary: dict[str, Any],
    q5_profile: dict[str, Any],
    q5_permission_boundary: dict[str, Any],
    q6_profile: dict[str, Any],
    safety_rejection_history: list[str],
    procedural_memory_constraints: list[str],
) -> dict[str, list[str]]:
    identity_constraints = _flatten_identity_kernel_constraints(identity_kernel)
    q3_constraints = _meaningful_text_list(
        q3_mission_boundary.get("continuity_boundaries") if isinstance(q3_mission_boundary, dict) else [],
        q3_mission_boundary.get("priority_duties") if isinstance(q3_mission_boundary, dict) else [],
    )
    q5_constraints = _q5_red_line_sources(q5_profile, q5_permission_boundary)
    cost_profile = q6_profile.get("CostImpactProfile") if isinstance(q6_profile, dict) else {}
    consequence_profile = q6_profile.get("ConsequenceAssessment") if isinstance(q6_profile, dict) else {}
    q6_constraints = _meaningful_text_list(
        q6_profile.get("absolute_red_lines") if isinstance(q6_profile, dict) else [],
        q6_profile.get("prohibited_strategies") if isinstance(q6_profile, dict) else [],
        q6_profile.get("performance_tradeoff_bans") if isinstance(q6_profile, dict) else [],
        cost_profile.get("security_compliance_impacts") if isinstance(cost_profile, dict) else [],
        cost_profile.get("stop_conditions") if isinstance(cost_profile, dict) else [],
        consequence_profile.get("downstream_consequences") if isinstance(consequence_profile, dict) else [],
    )
    non_bypassable_constraints = list(
        dict.fromkeys(
            item
            for item in (
                identity_constraints
                + q3_constraints
                + q5_constraints
                + q6_constraints
                + _meaningful_text_list(procedural_memory_constraints)
            )
            if normalize_text(item)
        )
    )
    source_explanations = []
    if identity_constraints:
        source_explanations.append("身份边界: " + " / ".join(identity_constraints[:6]))
    if q3_constraints:
        source_explanations.append("Q3 mission boundaries: " + " / ".join(q3_constraints[:6]))
    if q5_constraints:
        source_explanations.append("Q5 cannot-do boundary: " + " / ".join(q5_constraints[:6]))
    if q6_constraints:
        source_explanations.append("Q6 consequence/cost carryover: " + " / ".join(q6_constraints[:6]))
    if safety_rejection_history:
        source_explanations.append("安全与审计拒绝记录: " + " / ".join(safety_rejection_history[:6]))
    if procedural_memory_constraints:
        source_explanations.append("程序记忆约束: " + " / ".join(procedural_memory_constraints[:6]))
    return {
        "identity_kernel_constraints": identity_constraints,
        "q3_mission_boundary_constraints": q3_constraints,
        "authorization_boundary_constraints": q5_constraints,
        "safety_rejection_history": _meaningful_text_list(safety_rejection_history),
        "procedural_memory_constraints": _meaningful_text_list(procedural_memory_constraints),
        "non_bypassable_constraints": non_bypassable_constraints,
        "ban_source_explanations": source_explanations,
        "question_driver_refs": [
            ref
            for ref in [
                "Q7: 红线与约束评估",
                "Q3: 使命与连续性边界",
                "Q5: 禁止边界",
                "Q6: 代价与后果",
                "身份边界",
                "安全门 / 审计通道",
                "程序记忆",
            ]
            if normalize_text(ref)
        ],
    }
