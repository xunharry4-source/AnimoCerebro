from __future__ import annotations

from typing import Any


def _is_non_empty_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def assert_no_snapshot_fallback(diagnosis: dict[str, Any], question_id: str) -> None:
    if "snapshot_fallback_used" in diagnosis:
        assert diagnosis.get("snapshot_fallback_used") is False, (
            f"{question_id} used snapshot fallback; strict real-success gate rejects this run"
        )
    if "used_fallback" in diagnosis:
        assert diagnosis.get("used_fallback") is False, (
            f"{question_id} used fallback; strict real-success gate rejects this run"
        )


def assert_llm_output_integrity(
    *,
    question_id: str,
    composed: dict[str, Any],
    context_updates: dict[str, Any],
) -> None:
    inference_node = _as_dict(composed.get("inference"))
    assert inference_node, f"{question_id}: composed.inference is empty"

    if question_id == "q1":
        payload = _as_dict(context_updates.get("workspace_domain_inference"))
        assert _is_non_empty_text(payload.get("primary_domain")), "q1 LLM payload missing primary_domain"
        assert _is_non_empty_text(payload.get("reasoning_summary")), "q1 LLM payload missing reasoning_summary"
        assert _is_non_empty_text(payload.get("suggested_first_step")), "q1 LLM payload missing suggested_first_step"
        return

    if question_id == "q2":
        role = _as_dict(context_updates.get("q2_role_profile"))
        boundary = _as_dict(context_updates.get("q2_mission_boundary"))
        assert _is_non_empty_text(role.get("identity_role")), "q2 LLM payload missing identity_role"
        assert _is_non_empty_text(role.get("active_role")), "q2 LLM payload missing active_role"
        assert _is_non_empty_text(role.get("task_role")), "q2 LLM payload missing task_role"
        assert _is_non_empty_text(boundary.get("current_mission")), "q2 LLM payload missing current_mission"
        assert isinstance(boundary.get("continuity_boundaries"), list), "q2 LLM payload continuity_boundaries must be list"
        return

    if question_id == "q3":
        inventory = _as_dict(context_updates.get("q3_unified_asset_inventory"))
        evaluation = _as_dict(context_updates.get("q3_resource_evaluation"))
        assert isinstance(inventory.get("available_cognitive_tools"), list), "q3 LLM payload missing available_cognitive_tools"
        assert _is_non_empty_text(evaluation.get("resource_status")), "q3 LLM payload missing resource_status"
        assert _is_non_empty_text(evaluation.get("bottleneck_node")), "q3 LLM payload missing bottleneck_node"
        return

    if question_id == "q4":
        profile = _as_dict(context_updates.get("q4_capability_boundary_profile"))
        assert isinstance(profile.get("actionable_space"), list), "q4 LLM payload missing actionable_space"
        assert isinstance(profile.get("capability_upper_limits"), list), "q4 LLM payload missing capability_upper_limits"
        return

    if question_id == "q5":
        boundary = _as_dict(context_updates.get("q5_permission_boundary"))
        profile = _as_dict(context_updates.get("q5_authorization_boundary_profile"))
        assert isinstance(boundary.get("authorized_actions"), list), "q5 LLM payload missing authorized_actions"
        assert isinstance(boundary.get("unauthorized_actions"), list), "q5 LLM payload missing unauthorized_actions"
        assert isinstance(boundary.get("conditional_actions"), list), "q5 LLM payload missing conditional_actions"
        assert isinstance(profile.get("forbidden_action_space"), list), "q5 LLM payload missing forbidden_action_space"
        return

    if question_id == "q6":
        profile = _as_dict(context_updates.get("q6_forbidden_zone_profile"))
        assert isinstance(profile.get("absolute_red_lines"), list), "q6 LLM payload missing absolute_red_lines"
        assert isinstance(profile.get("prohibited_strategies"), list), "q6 LLM payload missing prohibited_strategies"
        return

    if question_id == "q7":
        profile = _as_dict(context_updates.get("q7_alternative_strategy_profile"))
        assert isinstance(profile.get("fallback_plans"), list), "q7 LLM payload missing fallback_plans"
        assert isinstance(profile.get("degradation_strategies"), list), "q7 LLM payload missing degradation_strategies"
        assert isinstance(profile.get("collaboration_switches"), list), "q7 LLM payload missing collaboration_switches"
        assert isinstance(profile.get("exploratory_actions"), list), "q7 LLM payload missing exploratory_actions"
        return

    if question_id == "q8":
        objective = _as_dict(context_updates.get("q8_objective_profile"))
        queue = _as_dict(context_updates.get("q8_task_queue"))
        assert _is_non_empty_text(objective.get("current_mission")), "q8 LLM payload missing current_mission"
        assert isinstance(objective.get("priority_order"), list), "q8 LLM payload missing priority_order"
        assert isinstance(queue.get("next_self_tasks"), list), "q8 LLM payload missing next_self_tasks"
        return

    if question_id == "q9":
        evaluation = _as_dict(context_updates.get("q9_evaluation_profile"))
        evolution = _as_dict(context_updates.get("q9_evolution_profile"))
        escalation = _as_dict(context_updates.get("q9_escalation_profile"))
        assert _is_non_empty_text(evaluation.get("role_context")), "q9 LLM payload missing role_context"
        assert _is_non_empty_text(evaluation.get("risk_level")), "q9 LLM payload missing risk_level"
        assert isinstance(evolution.get("allowed_directions"), list), "q9 LLM payload missing allowed_directions"
        assert isinstance(escalation.get("pause_conditions"), list), "q9 LLM payload missing pause_conditions"
        return

    raise AssertionError(f"Unknown question_id for llm integrity check: {question_id}")
