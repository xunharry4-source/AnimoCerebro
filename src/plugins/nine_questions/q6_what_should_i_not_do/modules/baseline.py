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


def normalize_redline_inputs(raw_inputs: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if isinstance(item, dict):
            normalized.append(dict(item))
        elif isinstance(item, list):
            normalized.append({"items": [str(entry).strip() for entry in item if str(entry).strip()]})
    return normalized


def derive_forbidden_zone_baseline(
    snapshot: dict[str, Any],
    global_constraints: list[dict[str, Any]],
    redline_hints: list[dict[str, Any]],
) -> dict[str, list[str]]:
    q4_profile = snapshot.get("q4_capability_boundary_profile")
    q4_profile = q4_profile if isinstance(q4_profile, dict) else {}
    q5_profile = snapshot.get("q5_authorization_boundary_profile")
    q5_profile = q5_profile if isinstance(q5_profile, dict) else {}
    q5_permission_boundary = snapshot.get("q5_permission_boundary")
    q5_permission_boundary = q5_permission_boundary if isinstance(q5_permission_boundary, dict) else {}

    absolute_red_lines: list[str] = []
    performance_tradeoff_bans: list[str] = []
    prohibited_strategies: list[str] = []
    contamination_risks: list[str] = []

    for item in global_constraints:
        constraints = coerce_string_list(item.get("non_bypassable_constraints"))
        absolute_red_lines.extend(constraints)
        contamination_risks.extend(coerce_string_list(item.get("contamination_risks")))

    for item in redline_hints:
        absolute_red_lines.extend(coerce_string_list(item.get("absolute_red_lines")))
        performance_tradeoff_bans.extend(coerce_string_list(item.get("performance_tradeoff_bans")))
        prohibited_strategies.extend(coerce_string_list(item.get("prohibited_strategies")))
        contamination_risks.extend(coerce_string_list(item.get("contamination_risks")))
        contamination_risks.extend(coerce_string_list(item.get("forbidden_actions")))
        contamination_risks.extend(coerce_string_list(item.get("items")))

    forbidden_actions = q5_profile.get("forbidden_action_space")
    if isinstance(forbidden_actions, list):
        for item in forbidden_actions:
            if isinstance(item, dict):
                action = normalize_text(item.get("action"))
                reason = normalize_text(item.get("reason"))
                if action and reason:
                    prohibited_strategies.append(f"{action}: {reason}")
                elif action:
                    prohibited_strategies.append(action)

    escalation_actions = coerce_string_list(q5_profile.get("requires_escalation_actions"))
    if escalation_actions:
        performance_tradeoff_bans.append("no bypassing escalation-required actions")
        prohibited_strategies.extend(
            [f"execute without escalation: {action}" for action in escalation_actions]
        )

    unauthorized_actions = coerce_string_list(q5_permission_boundary.get("unauthorized_actions"))
    prohibited_strategies.extend(unauthorized_actions)

    permission_profile = snapshot.get("q4_permission_profile")
    permission_profile = permission_profile if isinstance(permission_profile, dict) else {}
    if permission_profile.get("is_read_only") is True:
        performance_tradeoff_bans.append("no write-like actions in read-only mode")

    absolute_red_lines = list(dict.fromkeys(item for item in absolute_red_lines if normalize_text(item)))
    performance_tradeoff_bans = list(
        dict.fromkeys(item for item in performance_tradeoff_bans if normalize_text(item))
    )
    prohibited_strategies = list(
        dict.fromkeys(item for item in prohibited_strategies if normalize_text(item))
    )
    contamination_risks = list(
        dict.fromkeys(item for item in contamination_risks if normalize_text(item))
    )

    return {
        "absolute_red_lines": absolute_red_lines,
        "performance_tradeoff_bans": performance_tradeoff_bans,
        "prohibited_strategies": prohibited_strategies,
        "contamination_risks": contamination_risks,
    }


def merge_with_forbidden_baseline(inferred: list[str], baseline: list[str]) -> list[str]:
    return list(dict.fromkeys(coerce_string_list(inferred) + coerce_string_list(baseline)))
