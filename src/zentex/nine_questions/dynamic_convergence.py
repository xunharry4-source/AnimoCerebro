from __future__ import annotations

"""Deterministic convergence rules for Feature 57 objective profiles."""

from typing import Any


def apply_dynamic_convergence(
    *,
    snapshot_map: dict[str, dict[str, Any]],
    objective_payload: dict[str, Any],
    evaluation_payload: dict[str, Any],
    evolution_payload: dict[str, Any],
    resource_state: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    objective = dict(objective_payload)
    evaluation = dict(evaluation_payload)
    evolution = dict(evolution_payload)
    applied_rules: list[str] = []

    q3_state = _merge_dicts(_extract_state(snapshot_map.get("q3", {})), resource_state or {})
    if _resource_tight(q3_state):
        evaluation["evaluation_weights"] = _converge_risk_and_continuity_weights(
            _as_float_map(evaluation.get("evaluation_weights"))
        )
        applied_rules.append("q3_resource_tightness_converged_weights_to_risk_control_and_continuity")

    q4_state = _extract_state(snapshot_map.get("q4", {}))
    if _evidence_insufficient(q4_state):
        evaluation["conservative_mode_triggered"] = True
        if not str(evaluation.get("evaluation_style") or "").strip():
            evaluation["evaluation_style"] = "evidence_first"
        if not str(evaluation.get("action_rhythm_hint") or "").strip():
            evaluation["action_rhythm_hint"] = "confirm_before_action"
        applied_rules.append("q4_evidence_insufficient_triggered_conservative_mode")

    q5_state = _extract_state(snapshot_map.get("q5", {}))
    if _collaboration_unavailable(q5_state):
        objective = _shrink_to_single_brain_objectives(objective)
        applied_rules.append("q5_collaboration_unavailable_shrank_objectives_to_single_brain_scope")

    failure_history = history if history is not None else _extract_evolution_history(snapshot_map)
    if _continuous_failures(failure_history):
        current_threshold = _as_float(evolution.get("risk_threshold"), default=0.0)
        evolution["risk_threshold"] = min(current_threshold, 0.1)
        requirements = _string_list(evolution.get("validation_requirements"))
        requirement = "continuous failure history requires low-risk validation before evolution"
        if requirement not in requirements:
            requirements.append(requirement)
        evolution["validation_requirements"] = requirements
        applied_rules.append("evolution_history_continuous_failures_lowered_risk_threshold")

    return objective, evaluation, evolution, applied_rules


def _extract_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    context_updates = snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {}
    result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    merged: dict[str, Any] = {}
    for source in (result, context_updates):
        for key in (
            "resource_state",
            "q3_resource_state",
            "asset_state",
            "capability_state",
            "q4_capability_state",
            "authorization_state",
            "q5_authorization_state",
            "collaboration_state",
        ):
            value = source.get(key)
            if isinstance(value, dict):
                merged.update(value)
        merged.update({key: value for key, value in source.items() if key not in merged})
    return merged


def _extract_evolution_history(snapshot_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    for question_id in ("q9", "q7", "q6"):
        snapshot = snapshot_map.get(question_id, {})
        state = _extract_state(snapshot)
        for key in ("evolution_history", "failure_history", "recent_evolution_outcomes"):
            value = state.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _resource_tight(state: dict[str, Any]) -> bool:
    text = " ".join(
        str(state.get(key) or "").lower()
        for key in ("status", "resource_status", "asset_status", "resource_tension", "resource_context")
    )
    if any(token in text for token in ("tight", "scarce", "limited", "insufficient", "紧张", "不足", "受限")):
        return True
    for key in ("budget_remaining_ratio", "remaining_ratio", "resource_remaining_ratio"):
        if key in state and _as_float(state.get(key), default=1.0) <= 0.2:
            return True
    return bool(state.get("assets_insufficient") is True or state.get("resource_tight") is True)


def _evidence_insufficient(state: dict[str, Any]) -> bool:
    text = " ".join(
        str(state.get(key) or "").lower()
        for key in ("evidence_status", "capability_evidence_status", "capability_status")
    )
    if any(token in text for token in ("insufficient", "uncertain", "weak", "不足", "不确定")):
        return True
    for key in ("capability_confidence", "evidence_confidence"):
        if key in state and _as_float(state.get(key), default=1.0) < 0.5:
            return True
    return bool(state.get("capability_uncertain") is True or state.get("evidence_insufficient") is True)


def _collaboration_unavailable(state: dict[str, Any]) -> bool:
    if state.get("collaboration_available") is False:
        return True
    if state.get("external_agent_authorized") is False:
        return True
    text = " ".join(
        str(state.get(key) or "").lower()
        for key in ("authorization_scope", "collaboration_status", "resource_context")
    )
    return any(token in text for token in ("single_brain", "solo", "collaboration_unavailable", "协作不可用", "单脑"))


def _continuous_failures(history: list[dict[str, Any]] | None) -> bool:
    if not history:
        return False
    failures = 0
    for item in reversed(history):
        status = str(item.get("status") or item.get("outcome") or "").lower()
        if status in {"failed", "failure", "blocked", "rollback", "rolled_back", "失败", "回滚"}:
            failures += 1
            if failures >= 3:
                return True
        elif status in {"passed", "success", "succeeded", "成功"}:
            break
    return False


def _converge_risk_and_continuity_weights(weights: dict[str, float]) -> dict[str, float]:
    if not weights:
        return {"accuracy": 0.2, "risk_control": 0.5, "continuity": 0.3}
    risk = max(weights.get("risk_control", 0.0), 0.4)
    continuity = max(weights.get("continuity", 0.0), 0.25)
    remaining = max(0.0, 1.0 - risk - continuity)
    other_keys = [key for key in weights if key not in {"risk_control", "continuity"}]
    other_total = sum(max(weights[key], 0.0) for key in other_keys)
    converged: dict[str, float] = {"risk_control": round(risk, 6), "continuity": round(continuity, 6)}
    if other_keys:
        if other_total > 0:
            for key in other_keys:
                converged[key] = round(max(weights[key], 0.0) / other_total * remaining, 6)
        else:
            share = remaining / len(other_keys)
            for key in other_keys:
                converged[key] = round(share, 6)
    return {key: converged[key] for key in weights if key in converged}


def _shrink_to_single_brain_objectives(objective: dict[str, Any]) -> dict[str, Any]:
    explicit = _string_list(objective.get("single_brain_objectives"))
    if explicit:
        objective["primary_objectives"] = explicit
    else:
        primary = _filter_single_brain(_string_list(objective.get("primary_objectives")))
        if not primary:
            primary = _string_list(objective.get("current_primary_objective") or objective.get("current_mission"))
        objective["primary_objectives"] = primary
    if objective["primary_objectives"]:
        objective["current_primary_objective"] = objective["primary_objectives"][0]
        objective["current_mission"] = objective["primary_objectives"][0]
    objective["secondary_objectives"] = _filter_single_brain(_string_list(objective.get("secondary_objectives")))
    objective["current_phase_tasks"] = _filter_single_brain(_string_list(objective.get("current_phase_tasks")))
    objective["priority_order"] = _filter_single_brain(_string_list(objective.get("priority_order")))
    pause_conditions = _string_list(objective.get("pause_conditions"))
    pause = "collaboration unavailable: external-agent objectives deferred"
    if pause not in pause_conditions:
        pause_conditions.append(pause)
    objective["pause_conditions"] = pause_conditions
    return objective


def _filter_single_brain(items: list[str]) -> list[str]:
    return [item for item in items if not _requires_collaboration(item)]


def _requires_collaboration(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "collaborat",
            "external agent",
            "multi-agent",
            "delegate",
            "协作",
            "外部agent",
            "外部 agent",
            "多脑",
        )
    )


def _merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    merged.update(right)
    return merged


def _as_float_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        result[str(key)] = _as_float(item, default=0.0)
    return result


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []
