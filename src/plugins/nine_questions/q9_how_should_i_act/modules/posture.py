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


def normalize_ratio(value: object) -> float:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))
    return 0.0


def normalize_snapshot_dict(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if str(key).strip()}


def _extract_q8_summary_mission(question_snapshot: dict[str, Any]) -> str:
    summaries = question_snapshot.get("summaries")
    if not isinstance(summaries, dict):
        return ""
    summary_text = normalize_text(summaries.get("我现在应该做什么"))
    if not summary_text:
        return ""
    if "mission=" in summary_text:
        return normalize_text(summary_text.split("mission=", 1)[1])
    return summary_text


def normalize_q8_profile(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    objective = raw.get("objective")
    objective = objective if isinstance(objective, dict) else {}
    objective_profile = raw.get("q8_objective_profile")
    objective_profile = objective_profile if isinstance(objective_profile, dict) else {}

    current_mission = normalize_text(
        raw.get("current_mission")
        or objective.get("current_mission")
        or objective_profile.get("current_mission")
    )
    current_phase_tasks = coerce_string_list(
        raw.get("current_phase_tasks")
        or objective.get("current_phase_tasks")
        or objective_profile.get("current_phase_tasks")
    )
    priority_order = coerce_string_list(
        raw.get("priority_order")
        or objective.get("priority_order")
        or objective_profile.get("priority_order")
    )

    return {
        **raw,
        "current_mission": current_mission,
        "current_phase_tasks": current_phase_tasks,
        "priority_order": priority_order,
    }


def normalize_self_model(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    has_source = any(
        key in raw
        for key in (
            "current_cognitive_load",
            "cognitive_load",
            "current_state",
            "recent_weaknesses",
        )
    )
    if not has_source:
        return {}
    current_state = raw.get("current_state")
    current_state = current_state if isinstance(current_state, dict) else {}
    weaknesses = raw.get("recent_weaknesses")
    normalized_weaknesses: list[dict[str, Any]] = []
    if isinstance(weaknesses, list):
        for item in weaknesses:
            if not isinstance(item, dict):
                continue
            normalized_weaknesses.append(
                {
                    "pattern_id": normalize_text(item.get("pattern_id")) or None,
                    "pattern_type": normalize_text(item.get("pattern_type") or "unknown"),
                    "frequency": item.get("frequency") if isinstance(item.get("frequency"), int) else None,
                    "severity": normalize_text(item.get("severity")) or None,
                }
            )
    return {
        "cognitive_load": normalize_text(raw.get("current_cognitive_load") or raw.get("cognitive_load")),
        "stability_level": normalize_text(current_state.get("stability_level")) or None,
        "recent_weaknesses": normalized_weaknesses,
    }


def normalize_reasoning_budget(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    has_source = any(
        key in raw
        for key in (
            "compute_remaining_ratio",
            "remaining",
            "compute_remaining",
            "token_remaining_ratio",
            "token_remaining",
            "time_remaining_ratio",
            "time_remaining",
            "budget_pressure",
        )
    )
    if not has_source:
        return {}
    return {
        "compute_remaining_ratio": normalize_ratio(
            raw.get("compute_remaining_ratio") or raw.get("remaining") or raw.get("compute_remaining")
        ),
        "token_remaining_ratio": normalize_ratio(
            raw.get("token_remaining_ratio") or raw.get("token_remaining")
        ),
        "time_remaining_ratio": normalize_ratio(
            raw.get("time_remaining_ratio") or raw.get("time_remaining")
        ),
        "budget_pressure": normalize_text(raw.get("budget_pressure")) or None,
    }


def normalize_functional_postures(raw_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        normalized.append(
            {
                "plugin_id": normalize_text(item.get("plugin_id")),
                "evaluation_style": normalize_text(result.get("evaluation_style")),
                "risk_level": normalize_text(result.get("risk_level")),
                "allowed_directions": coerce_string_list(result.get("allowed_directions")),
                "forbidden_directions": coerce_string_list(result.get("forbidden_directions")),
                "validation_requirements": coerce_string_list(result.get("validation_requirements")),
                "pause_conditions": coerce_string_list(result.get("pause_conditions")),
                "help_request_conditions": coerce_string_list(result.get("help_request_conditions")),
                "confirmation_required_conditions": coerce_string_list(result.get("confirmation_required_conditions")),
                "rollback_conditions": coerce_string_list(result.get("rollback_conditions")),
            }
        )
    return normalized


def derive_posture_baseline(
    question_snapshot: dict[str, Any],
    self_model: dict[str, Any],
    budget: dict[str, Any],
    functional_postures: list[dict[str, Any]],
) -> dict[str, Any]:
    q2 = question_snapshot.get("q2") if isinstance(question_snapshot.get("q2"), dict) else {}
    q3 = question_snapshot.get("q3") if isinstance(question_snapshot.get("q3"), dict) else {}
    q6 = question_snapshot.get("q6") if isinstance(question_snapshot.get("q6"), dict) else {}
    q8 = normalize_q8_profile(question_snapshot.get("q8"))
    summary_mission = _extract_q8_summary_mission(question_snapshot)
    current_mission = summary_mission or normalize_text(q8.get("current_mission"))

    role_context = normalize_text(q2.get("active_role") or q2.get("task_role") or q2.get("identity_role"))
    resource_context_parts: list[str] = []
    bottleneck = normalize_text(q3.get("bottleneck_node"))
    if bottleneck:
        resource_context_parts.append(f"bottleneck={bottleneck}")
    missing_assets = coerce_string_list(q3.get("missing_critical_assets"))
    if missing_assets:
        resource_context_parts.append(f"missing_assets={len(missing_assets)}")
    budget_pressure = normalize_text(budget.get("budget_pressure"))
    if budget_pressure:
        resource_context_parts.append(f"budget_pressure={budget_pressure}")
    compute_ratio = normalize_ratio(budget.get("compute_remaining_ratio"))
    token_ratio = normalize_ratio(budget.get("token_remaining_ratio"))
    time_ratio = normalize_ratio(budget.get("time_remaining_ratio"))
    stability_level = normalize_text(self_model.get("stability_level")).lower()
    red_lines = coerce_string_list(q6.get("absolute_red_lines"))

    conservative = (
        bool(red_lines)
        or stability_level in {"low", "fragile", "unstable"}
        or any(ratio and ratio < 0.3 for ratio in (compute_ratio, token_ratio, time_ratio))
    )
    risk_level = "high" if conservative else "medium"
    evaluation_style = "evidence_first" if conservative else "goal_balanced"
    action_rhythm = "confirm_before_commit" if conservative else "steady_incremental"

    priority_order = coerce_string_list(q8.get("priority_order"))
    current_phase_tasks = coerce_string_list(q8.get("current_phase_tasks"))

    if summary_mission:
        priority_order = [summary_mission, *[item for item in priority_order if normalize_text(item) != summary_mission]]
        current_phase_tasks = [summary_mission, *[item for item in current_phase_tasks if normalize_text(item) != summary_mission]]

    if not priority_order and current_mission:
        priority_order = [current_mission]

    if not current_phase_tasks and current_mission:
        current_phase_tasks = [current_mission]

    validation_requirements = [f"validate before action: {item}" for item in red_lines]
    validation_requirements.extend([f"protect objective continuity: {item}" for item in priority_order])

    allowed_directions = [f"advance current objective: {item}" for item in current_phase_tasks]
    forbidden_directions = [f"avoid red-line direction: {item}" for item in red_lines]
    pause_conditions = [f"pause on budget exhaustion: {label}" for label, ratio in (("compute", compute_ratio), ("token", token_ratio), ("time", time_ratio)) if ratio and ratio < 0.15]
    help_request_conditions = [f"request help for missing asset: {item}" for item in missing_assets]
    confirmation_required_conditions = [f"confirmation required for unstable posture: {item}" for item in red_lines]
    rollback_conditions = [f"rollback on forbidden direction: {item}" for item in forbidden_directions]

    for item in functional_postures:
        allowed_directions.extend(coerce_string_list(item.get("allowed_directions")))
        forbidden_directions.extend(coerce_string_list(item.get("forbidden_directions")))
        validation_requirements.extend(coerce_string_list(item.get("validation_requirements")))
        pause_conditions.extend(coerce_string_list(item.get("pause_conditions")))
        help_request_conditions.extend(coerce_string_list(item.get("help_request_conditions")))
        confirmation_required_conditions.extend(coerce_string_list(item.get("confirmation_required_conditions")))
        rollback_conditions.extend(coerce_string_list(item.get("rollback_conditions")))
        if not conservative and normalize_text(item.get("evaluation_style")):
            evaluation_style = normalize_text(item.get("evaluation_style"))
        if not conservative and normalize_text(item.get("risk_level")):
            risk_level = normalize_text(item.get("risk_level"))

    return {
        "evaluation_profile": {
            "role_context": role_context,
            "resource_context": "; ".join(resource_context_parts),
            "risk_level": risk_level,
            "evaluation_style": evaluation_style,
            "conservative_mode_triggered": conservative,
            "action_rhythm_hint": action_rhythm,
        },
        "evolution_profile": {
            "allowed_directions": list(dict.fromkeys(item for item in allowed_directions if normalize_text(item))),
            "forbidden_directions": list(dict.fromkeys(item for item in forbidden_directions if normalize_text(item))),
            "validation_requirements": list(dict.fromkeys(item for item in validation_requirements if normalize_text(item))),
            "risk_threshold": 0.05 if conservative else 0.15,
        },
        "escalation_profile": {
            "pause_conditions": list(dict.fromkeys(item for item in pause_conditions if normalize_text(item))),
            "help_request_conditions": list(dict.fromkeys(item for item in help_request_conditions if normalize_text(item))),
            "confirmation_required_conditions": list(dict.fromkeys(item for item in confirmation_required_conditions if normalize_text(item))),
            "rollback_conditions": list(dict.fromkeys(item for item in rollback_conditions if normalize_text(item))),
        },
    }
