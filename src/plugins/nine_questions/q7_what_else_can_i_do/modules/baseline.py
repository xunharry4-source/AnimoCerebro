from __future__ import annotations

from typing import Any


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
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


def _q5_permission_boundary_lines(q5_profile: dict[str, Any], q5_permission_boundary: dict[str, Any]) -> list[str]:
    merged = _meaningful_text_list(
        q5_profile.get("allowed_action_space"),
        q5_profile.get("allowed_actions"),
        q5_permission_boundary.get("authorized_actions"),
        q5_permission_boundary.get("conditional_actions"),
        q5_permission_boundary.get("unauthorized_actions"),
    )
    if merged:
        return merged

    contact_boundaries = q5_profile.get("contact_and_org_boundaries")
    if not isinstance(contact_boundaries, dict):
        return []

    flattened: list[str] = []
    for key in ("execution_tier", "interaction_scope", "requires_human_confirmation", "requires_cloud_audit"):
        raw = contact_boundaries.get(key)
        if raw in (None, "", [], {}):
            continue
        flattened.append(f"{key}={str(raw).strip()}")
    return list(dict.fromkeys(entry for entry in flattened if normalize_text(entry)))


def _historical_failure_patches(functional_alternatives: list[dict[str, Any]]) -> list[str]:
    patches: list[str] = []
    for item in functional_alternatives:
        if not isinstance(item, dict):
            continue
        patches.extend(coerce_string_list(item.get("historical_failure_patches")))
    return list(dict.fromkeys(entry for entry in patches if normalize_text(entry)))


def normalize_functional_alternatives(raw_inputs: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if isinstance(item, dict):
            entry = dict(item)
            for key in (
                "fallback_plans",
                "degradation_strategies",
                "collaboration_switches",
                "exploratory_actions",
                "resource_bottlenecks",
                "capability_limits",
                "permission_boundaries",
                "absolute_red_lines",
                "historical_failure_patches",
            ):
                if key in entry:
                    entry[key] = coerce_string_list(entry.get(key))
            normalized.append(entry)
        elif isinstance(item, list):
            normalized.append({"items": [str(entry).strip() for entry in item if str(entry).strip()]})
    return normalized


def derive_alternative_strategy_baseline(
    snapshot: dict[str, Any],
    functional_alternatives: list[dict[str, Any]],
) -> dict[str, list[str]]:
    q3_eval = snapshot.get("q3_resource_evaluation")
    q3_eval = q3_eval if isinstance(q3_eval, dict) else {}
    q4_profile = snapshot.get("q4_capability_boundary_profile")
    q4_profile = q4_profile if isinstance(q4_profile, dict) else {}
    q5_profile = snapshot.get("q5_authorization_boundary_profile")
    q5_profile = q5_profile if isinstance(q5_profile, dict) else {}
    q6_profile = snapshot.get("q6_forbidden_zone_profile")
    q6_profile = q6_profile if isinstance(q6_profile, dict) else {}

    fallback_plans: list[str] = []
    degradation_strategies: list[str] = []
    collaboration_switches: list[str] = []
    exploratory_actions: list[str] = []

    missing_assets = coerce_string_list(q3_eval.get("missing_critical_assets"))
    bottleneck_node = normalize_text(q3_eval.get("bottleneck_node"))
    for asset in missing_assets:
        exploratory_actions.append(f"inspect missing asset gap: {asset}")
        collaboration_switches.append(f"request support for missing asset: {asset}")
    if bottleneck_node:
        fallback_plans.append(f"route around bottleneck node: {bottleneck_node}")
        exploratory_actions.append(f"profile bottleneck constraints: {bottleneck_node}")

    capability_limits = coerce_string_list(q4_profile.get("capability_upper_limits"))
    actionable_space = coerce_string_list(q4_profile.get("actionable_space"))
    if capability_limits:
        degradation_strategies.extend([f"degrade around capability limit: {item}" for item in capability_limits])
    if not actionable_space:
        fallback_plans.append("switch to information-gathering only until actionable_space is rebuilt")

    escalation_actions = coerce_string_list(q5_profile.get("requires_escalation_actions"))
    allowed_delegation_targets = coerce_string_list(q5_profile.get("allowed_delegation_targets"))
    for action in escalation_actions:
        collaboration_switches.append(f"escalate before executing restricted action: {action}")
    if allowed_delegation_targets:
        collaboration_switches.extend([f"delegate through approved target: {item}" for item in allowed_delegation_targets])
    else:
        collaboration_switches.append("fallback to human confirmation when delegation target is unclear")

    absolute_red_lines = coerce_string_list(q6_profile.get("absolute_red_lines"))
    prohibited_strategies = coerce_string_list(q6_profile.get("prohibited_strategies"))
    if absolute_red_lines or prohibited_strategies:
        degradation_strategies.append("replace blocked primary path with compliant low-risk read/inspect workflow")
    for item in absolute_red_lines:
        fallback_plans.append(f"avoid red-line path and choose compliant branch: {item}")

    for item in functional_alternatives:
        fallback_plans.extend(coerce_string_list(item.get("fallback_plans")))
        fallback_plans.extend(coerce_string_list(item.get("alternative_candidates")))
        degradation_strategies.extend(coerce_string_list(item.get("degradation_strategies")))
        collaboration_switches.extend(coerce_string_list(item.get("collaboration_switches")))
        exploratory_actions.extend(coerce_string_list(item.get("exploratory_actions")))
        fallback_plans.extend([f"fallback from plugin item: {entry}" for entry in coerce_string_list(item.get("items"))])

    return {
        "fallback_plans": list(dict.fromkeys(item for item in fallback_plans if normalize_text(item))),
        "degradation_strategies": list(dict.fromkeys(item for item in degradation_strategies if normalize_text(item))),
        "collaboration_switches": list(dict.fromkeys(item for item in collaboration_switches if normalize_text(item))),
        "exploratory_actions": list(dict.fromkeys(item for item in exploratory_actions if normalize_text(item))),
    }


def build_q7_baseline_modules(snapshot: dict[str, Any], functional_alternatives: list[dict[str, Any]]) -> dict[str, Any]:
    q3_eval = snapshot.get("q3_resource_evaluation") or {}
    q4_profile = snapshot.get("q4_capability_boundary_profile") or {}
    q5_profile = snapshot.get("q5_authorization_boundary_profile") or snapshot.get("q5_permission_boundary") or {}
    q5_permission_boundary = snapshot.get("q5_permission_boundary") or {}
    q6_profile = snapshot.get("q6_forbidden_zone_profile") or {}
    baseline = derive_alternative_strategy_baseline(snapshot, functional_alternatives)

    return {
        "resource_bottleneck_projection": {
            "resource_bottlenecks": _meaningful_text_list(
                q3_eval.get("missing_critical_assets"),
                q3_eval.get("bottleneck_node"),
            ),
        },
        "capability_limit_projection": {
            "capability_limits": coerce_string_list(q4_profile.get("capability_upper_limits")),
        },
        "permission_boundary_projection": {
            "permission_boundaries": _q5_permission_boundary_lines(
                q5_profile if isinstance(q5_profile, dict) else {},
                q5_permission_boundary if isinstance(q5_permission_boundary, dict) else {},
            ),
        },
        "absolute_redline_projection": {
            "absolute_red_lines": coerce_string_list(q6_profile.get("absolute_red_lines")),
        },
        "historical_failure_patch_projection": {
            "historical_failure_patches": _historical_failure_patches(functional_alternatives),
        },
        "fallback_plan_inference": {"fallback_plans": baseline.get("fallback_plans", [])},
        "degradation_strategy_inference": {"degradation_strategies": baseline.get("degradation_strategies", [])},
        "collaboration_switch_inference": {"collaboration_switches": baseline.get("collaboration_switches", [])},
        "exploratory_action_inference": {"exploratory_actions": baseline.get("exploratory_actions", [])},
    }


def merge_with_strategy_baseline(inferred: list[str], baseline: list[str]) -> list[str]:
    return list(dict.fromkeys(coerce_string_list(inferred) + coerce_string_list(baseline)))
