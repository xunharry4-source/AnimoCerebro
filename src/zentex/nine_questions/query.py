from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
from typing import Any

logger = logging.getLogger(__name__)

COMPOSED_RECORD_SCHEMA_VERSION = 3

from zentex.web_console.routers.nine_questions_impl.evidence_q1 import (
    _extract_q1_inference_result,
    _extract_q1_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q2 import (
    _extract_q2_inference_result,
    _extract_q2_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q3 import (
    _extract_q3_inference_result,
    _extract_q3_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q4 import (
    _extract_q4_inference_result,
    _extract_q4_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q5 import (
    _extract_q5_inference_result,
    _extract_q5_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q6 import (
    _extract_q6_inference_result,
    _extract_q6_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q7 import (
    _extract_q7_inference_result,
    _extract_q7_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q8 import (
    _extract_q8_inference_result,
    _extract_q8_preprocessed_evidence,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q9 import (
    _extract_q9_inference_result,
    _extract_q9_preprocessed_evidence,
)


QUESTION_EXTRACTORS = {
    "q1": {"evidence": _extract_q1_preprocessed_evidence, "result": _extract_q1_inference_result},
    "q2": {"evidence": _extract_q2_preprocessed_evidence, "result": _extract_q2_inference_result},
    "q3": {"evidence": _extract_q3_preprocessed_evidence, "result": _extract_q3_inference_result},
    "q4": {"evidence": _extract_q4_preprocessed_evidence, "result": _extract_q4_inference_result},
    "q5": {"evidence": _extract_q5_preprocessed_evidence, "result": _extract_q5_inference_result},
    "q6": {"evidence": _extract_q6_preprocessed_evidence, "result": _extract_q6_inference_result},
    "q7": {"evidence": _extract_q7_preprocessed_evidence, "result": _extract_q7_inference_result},
    "q8": {"evidence": _extract_q8_preprocessed_evidence, "result": _extract_q8_inference_result},
    "q9": {"evidence": _extract_q9_preprocessed_evidence, "result": _extract_q9_inference_result},
}


QUESTION_MODULE_IDS: dict[str, list[str]] = {
    "q1": [
        "dependency_check",
        "functional_plugin_chain",
        "environment_service",
        "environment_scan",
        "workspace_structure_scan",
        "content_sampling",
        "uncertainty_projection",
        "domain_inference",
        "state_write",
    ],
    "q2": [
        "identity_kernel_builder",
        "role_candidates",
        "risk_preference_projection",
        "mission_continuity_projection",
        "role_inference",
    ],
    "q3": [
        "workspace_permission_inventory",
        "cognitive_tools_inventory",
        "execution_tools_inventory",
        "connected_agents_inventory",
        "mcp_inventory",
        "cli_inventory",
        "external_connectors_inventory",
        "memory_strategy_inventory",
        "resource_sufficiency_inference",
    ],
    "q4": [
        "q1_context_projection",
        "q2_context_projection",
        "q3_inventory_projection",
        "capability_limits_inference",
        "actionable_space_inference",
        "strategy_inference",
    ],
    "q5": [
        "actionable_space_projection",
        "contact_policy_projection",
        "tenant_boundary_projection",
        "agent_trust_projection",
        "authorization_inference",
        "compliance_inference",
    ],
    "q6": [
        "authorization_boundary_projection",
        "non_bypassable_constraints_projection",
        "historical_strategy_patch_projection",
        "q6_consequence_projection",
        "consequence_assessment_inference",
        "cost_impact_inference",
        "mitigation_requirement_inference",
        "q6_evolution_projection",
        "capability_gap_inference",
        "recommended_expansion_inference",
        "evolution_profile_inference",
        "validation_requirement_inference",
        "q6_forbidden_projection",
    ],
    "q7": [
        "resource_bottleneck_projection",
        "capability_limit_projection",
        "permission_boundary_projection",
        "absolute_redline_projection",
        "historical_failure_patch_projection",
        "fallback_plan_inference",
        "degradation_strategy_inference",
        "collaboration_switch_inference",
        "exploratory_action_inference",
    ],
    "q8": [
        "aggregated_context_projection",
        "persistent_task_state_projection",
        "cognitive_agenda_projection",
        "objective_inference",
        "task_queue_inference",
        "priority_order_inference",
    ],
    "q9": [
        "cognitive_snapshot_projection",
        "self_model_projection",
        "reasoning_budget_projection",
        "action_posture_inference",
        "risk_tolerance_inference",
        "confirmation_strategy_inference",
        "evolution_direction_inference",
    ],
}


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(value, dict):
        return deepcopy(value)
    return {}


def _merge_missing_fields(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(target)
    for key, value in source.items():
        if merged.get(key) in (None, "", [], {}):
            merged[key] = deepcopy(value)
    return merged


def _has_q2_asset_inventory_rows(value: Any) -> bool:
    inventory = _as_dict(value)
    return any(isinstance(item, list) and len(item) > 0 for item in inventory.values())


def _merge_q2_asset_projection(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    if not fallback:
        return primary
    merged = deepcopy(primary)
    if not _has_q2_asset_inventory_rows(merged.get("asset_inventory")) and _has_q2_asset_inventory_rows(
        fallback.get("asset_inventory")
    ):
        merged["asset_inventory"] = deepcopy(fallback["asset_inventory"])
    for key in ("workspace_permission", "tools_agents", "memory_strategy", "sufficiency_assessment"):
        if merged.get(key) in (None, "", [], {}) and fallback.get(key) not in (None, "", [], {}):
            merged[key] = deepcopy(fallback[key])
    return merged


def _question_number(question_id: str) -> Optional[int]:
    if not isinstance(question_id, str) or not question_id.startswith("q"):
        return None
    suffix = question_id[1:]
    return int(suffix) if suffix.isdigit() else None


def _merge_snapshot_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("result", "context_updates", "execution_result"):
        payload = _as_dict(snapshot.get(key))
        if payload:
            merged.update(payload)
    return merged


def _merge_llm_trace_payload(primary: Any, fallback: Any) -> dict[str, Any]:
    merged = _as_dict(primary)
    fallback_payload = _as_dict(fallback)
    if not fallback_payload:
        return merged
    if not merged:
        return deepcopy(fallback_payload)
    for key, value in fallback_payload.items():
        if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = deepcopy(value)
    return merged


def _unwrap_q7_red_line_assessment(payload: Any) -> dict[str, Any]:
    assessment = _as_dict(payload)
    wrapped = assessment.get("RedLineAssessment")
    return _as_dict(wrapped) if isinstance(wrapped, dict) else assessment


def _module_payload_data(module_payload: Any) -> dict[str, Any]:
    if not isinstance(module_payload, dict):
        return {}
    data = module_payload.get("data")
    return _as_dict(data) if isinstance(data, dict) else {}


def _inject_module_outputs_into_projection(
    question_id: str,
    context_updates: dict[str, Any],
    result_payload: dict[str, Any],
    module_payloads: dict[str, Optional[Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not module_payloads:
        return context_updates, result_payload

    merged_context = deepcopy(context_updates)
    merged_result = deepcopy(result_payload)

    def _set_context(key: str, value: Any) -> None:
        if value not in (None, "", [], {}):
            merged_context[key] = deepcopy(value)

    def _set_result(key: str, value: Any) -> None:
        if value not in (None, "", [], {}):
            merged_result[key] = deepcopy(value)

    if question_id == "q2":
        asset_inventory = _as_dict(merged_context.get("q2_asset_inventory") or merged_result.get("asset_inventory"))
        if asset_inventory:
            _set_result("asset_inventory", asset_inventory)
            _set_context("q2_asset_inventory", asset_inventory)
        inventory = _as_dict(merged_context.get("q2_unified_asset_inventory"))
        workspace = _module_payload_data(module_payloads.get("workspace_permission_inventory"))
        if workspace:
            if isinstance(workspace.get("accessible_workspace_zones"), list):
                inventory["accessible_workspace_zones"] = deepcopy(workspace.get("accessible_workspace_zones"))
            if isinstance(workspace.get("tenant_permissions"), list):
                inventory["tenant_permissions"] = deepcopy(workspace.get("tenant_permissions"))
            _set_context("workspaces_and_permissions", workspace)
        cognitive = _module_payload_data(module_payloads.get("cognitive_tools_inventory"))
        if isinstance(cognitive.get("cognitive_tools"), list):
            inventory["available_cognitive_tools"] = deepcopy(cognitive.get("cognitive_tools"))
        execution = _module_payload_data(module_payloads.get("execution_tools_inventory"))
        if isinstance(execution.get("execution_tools"), list):
            inventory["available_execution_tools"] = deepcopy(execution.get("execution_tools"))
        connected = _module_payload_data(module_payloads.get("connected_agents_inventory"))
        if isinstance(connected.get("connected_agents"), list):
            inventory["connected_agents"] = deepcopy(connected.get("connected_agents"))
        mcp = _module_payload_data(module_payloads.get("mcp_inventory"))
        if isinstance(mcp.get("mcp_servers"), list):
            inventory["mcp_servers"] = deepcopy(mcp.get("mcp_servers"))
        cli = _module_payload_data(module_payloads.get("cli_inventory"))
        if isinstance(cli.get("cli_tools"), list):
            inventory["cli_tools"] = deepcopy(cli.get("cli_tools"))
        memory = _module_payload_data(module_payloads.get("memory_strategy_inventory"))
        if memory:
            inventory.update(deepcopy(memory))
            _set_context("memory_and_strategy", memory)
        _set_context("q2_unified_asset_inventory", inventory)
        sufficiency = _module_payload_data(module_payloads.get("q2_resource_sufficiency_inference"))
        _set_result("resource_evaluation", sufficiency)
        _set_context("q2_resource_evaluation", sufficiency)
    elif question_id == "q3":
        q1_dep = _module_payload_data(module_payloads.get("q3_q1_dependency_validation"))
        if q1_dep:
            _set_context("q1_environment_inference", q1_dep.get("workspace_domain_inference") or q1_dep)
            _set_context("q1_llm_trace_payload", q1_dep.get("q1_llm_trace_payload"))
        q2_dep = _module_payload_data(module_payloads.get("q3_q2_asset_dependency_validation"))
        if q2_dep:
            _set_context("q2_asset_inventory", q2_dep.get("q2_asset_inventory"))
            _set_context("q2_resource_evaluation", q2_dep.get("q2_resource_evaluation"))
            _set_context("q2_llm_trace_payload", q2_dep.get("q2_llm_trace_payload"))
        role = _module_payload_data(module_payloads.get("q3_role_reasoning_projection"))
        q3_result = role.get("Q3InferenceResult") if isinstance(role.get("Q3InferenceResult"), dict) else {}
        _set_result("Q3InferenceResult", q3_result)
        _set_context("q3_role_profile", q3_result.get("RoleProfile"))
        _set_context("q3_mission_boundary", q3_result.get("MissionContinuityBoundary"))
    elif question_id == "q4":
        inventory = _module_payload_data(module_payloads.get("q4_inventory_validation"))
        for key in ("q1_scene_model", "q1_uncertainty_profile", "q2_unified_asset_inventory", "q2_resource_evaluation", "q3_role_profile", "q3_mission_boundary"):
            _set_context(key, inventory.get(key))
        permission = _module_payload_data(module_payloads.get("q4_permission_validation"))
        _set_context("q4_permission_profile", permission.get("q4_permission_profile") or permission)
        baseline = _module_payload_data(module_payloads.get("q4_execution_capability_verification"))
        baseline_payload = baseline.get("q4_capability_baseline") or baseline
        _set_context("q4_capability_baseline", baseline_payload)
        _set_context("q4_active_execution_domains", baseline.get("q4_active_execution_domains") or baseline.get("active_execution_domains"))
        reasoning = _module_payload_data(module_payloads.get("q4_capability_reasoning_projection"))
        boundary = _module_payload_data(module_payloads.get("q4_capability_boundary_projection"))
        profile = boundary or reasoning
        _set_result("capability_boundary_profile", profile)
        _set_context("q4_capability_boundary_profile", profile)
    elif question_id == "q5":
        q4_boundary = _module_payload_data(module_payloads.get("q5_q4_boundary_validation"))
        _set_context("q4_capability_boundary_profile", q4_boundary.get("q4_capability_boundary_profile") or q4_boundary)
        tenant = _module_payload_data(module_payloads.get("q5_tenant_scope_validation"))
        _set_context("tenant_scope", tenant.get("tenant_scope") or tenant)
        contact = _module_payload_data(module_payloads.get("q5_contact_policy_validation"))
        _set_context("contact_policy", contact.get("contact_policy") or contact)
        trust = _module_payload_data(module_payloads.get("q5_agent_trust_validation"))
        _set_context("q5_agent_trust_status", trust.get("q5_agent_trust_status") or trust.get("agent_trust_status") or trust)
        decision = _module_payload_data(module_payloads.get("q5_authorization_decision_projection"))
        _set_result("authorization_boundary", decision.get("authorization_boundary"))
        _set_result("authorization_boundary_profile", decision.get("authorization_boundary_profile") or decision)
        _set_result("permission_boundary", decision.get("permission_boundary"))
        _set_context("q5_authorization_boundary", decision.get("authorization_boundary"))
        _set_context("q5_authorization_boundary_profile", decision.get("authorization_boundary_profile") or decision)
        _set_context("q5_permission_boundary", decision.get("permission_boundary"))
        _set_context("q5_objective_convergence_guard", decision.get("q5_objective_convergence_guard"))
    elif question_id == "q6":
        q4_boundary = _module_payload_data(module_payloads.get("q6_q4_boundary_validation"))
        _set_context("q4_capability_boundary_profile", q4_boundary.get("q4_capability_boundary_profile") or q4_boundary)
        q5_boundary = _module_payload_data(module_payloads.get("q6_q5_boundary_validation"))
        _set_context("q5_permission_boundary", q5_boundary.get("q5_permission_boundary") or q5_boundary)
        _set_context("q6_redline_hints", _module_payload_data(module_payloads.get("q6_redline_hint_chain")))
        _set_context(
            "q6_global_constraints",
            _module_payload_data(module_payloads.get("q6_global_constraint_projection"))
            or _module_payload_data(module_payloads.get("q6_constraint_source_validation")),
        )
        baseline = _module_payload_data(module_payloads.get("q6_risk_assessment"))
        _set_context("q6_forbidden_zone_baseline", baseline.get("q6_forbidden_zone_baseline") or baseline)
        forbidden = (
            _module_payload_data(module_payloads.get("q6_consequence_projection"))
            or _module_payload_data(module_payloads.get("q6_evolution_projection"))
            or _module_payload_data(module_payloads.get("evolution_profile_inference"))
            or _module_payload_data(module_payloads.get("capability_gap_inference"))
            or _module_payload_data(module_payloads.get("recommended_expansion_inference"))
            or _module_payload_data(module_payloads.get("validation_requirement_inference"))
        )
        if forbidden:
            consequence_assessment = None
            cost_impact_profile = None
            if isinstance(forbidden, dict):
                consequence_assessment = forbidden.get("ConsequenceAssessment") or forbidden.get("consequence_assessment")
                cost_impact_profile = forbidden.get("CostImpactProfile") or forbidden.get("cost_impact_profile")
            if consequence_assessment:
                _set_result("ConsequenceAssessment", consequence_assessment)
                _set_context("q6_consequence_assessment", consequence_assessment)
            if cost_impact_profile:
                _set_result("CostImpactProfile", cost_impact_profile)
                _set_context("q6_cost_impact_profile", cost_impact_profile)
        forbidden = (
            _module_payload_data(module_payloads.get("q6_forbidden_zone_projection"))
            or _module_payload_data(module_payloads.get("q6_forbidden_projection"))
        )
        _set_result("forbidden_zone_profile", forbidden)
        _set_context("q6_forbidden_zone_profile", forbidden)
    elif question_id == "q7":
        deps = _module_payload_data(module_payloads.get("q7_dependency_validation"))
        for key in (
            "identity_kernel_snapshot",
            "q5_authorization_boundary_profile",
            "q5_permission_boundary",
            "q6_consequence_profile",
            "q6_forbidden_zone_profile",
            "safety_rejection_history",
            "procedural_memory_constraints",
            "q7_red_line_baseline",
        ):
            _set_context(key, deps.get(key))
        baseline = _module_payload_data(module_payloads.get("q7_red_line_baseline_projection"))
        _set_context("q7_red_line_baseline", baseline)
        assessment = (
            _module_payload_data(module_payloads.get("q7_red_line_assessment_projection"))
            or _module_payload_data(module_payloads.get("q7_alternative_projection"))
        )
        assessment_body = _unwrap_q7_red_line_assessment(assessment)
        _set_result("red_line_assessment", assessment)
        _set_context("q7_red_line_assessment", assessment)
        _set_context("q7_current_redline_hits", assessment_body.get("current_redline_hits"))
        _set_context("q7_current_red_line_hits", assessment_body.get("current_red_line_hits") or assessment_body.get("current_redline_hits"))
        _set_context("q7_rejected_operations_log", assessment_body.get("rejected_operations_log"))
        _set_context("q7_rejected_operation_records", assessment_body.get("rejected_operation_records") or assessment_body.get("rejected_operations_log"))
        _set_context("q7_constraint_sources_explanation", assessment_body.get("constraint_sources_explanation"))
        _set_context("q7_ban_source_explanations", assessment_body.get("ban_source_explanations") or assessment_body.get("constraint_sources_explanation"))
        _set_context("q7_non_bypassable_constraints", assessment_body.get("non_bypassable_constraints"))
        _set_context("q7_question_driver_refs", assessment_body.get("question_driver_refs"))
        _set_context("q7_absolute_red_lines", assessment_body.get("non_bypassable_constraints"))
    elif question_id == "q8":
        snapshot = _module_payload_data(module_payloads.get("q8_snapshot_validation"))
        _set_context("q8_q1_q7_snapshot", snapshot.get("q8_q1_q7_snapshot") or snapshot)
        task_state = _module_payload_data(module_payloads.get("q8_task_state_load"))
        _set_context("q8_persistent_task_state", task_state.get("persistent_task_state") or task_state)
        objective_chain = _module_payload_data(module_payloads.get("q8_functional_objective_chain"))
        _set_context("q8_cognitive_agenda", objective_chain.get("cognitive_agenda") or objective_chain)
        priority = _module_payload_data(module_payloads.get("q8_priority_derivation"))
        _set_context("q8_priority_baseline", priority)
        decision = _module_payload_data(module_payloads.get("q8_decision_projection"))
        _set_result("objective_profile", decision.get("objective_profile"))
        _set_result("task_queue", decision.get("task_queue"))
        if decision:
            _set_result("q8_objective_and_queue", decision)
        internal_generation = _module_payload_data(module_payloads.get("q8_internal_task_generation"))
        internal_llm_output = _as_dict(internal_generation.get("q8_internal_llm_output"))
        if internal_llm_output:
            _set_result("q8_internal_llm_output", internal_llm_output)
            _set_context("q8_internal_llm_output", internal_llm_output)
            _set_result("q8_internal_cognitive_tasks", internal_llm_output.get("internal_cognitive_tasks"))
            _set_context("q8_internal_cognitive_tasks", internal_llm_output.get("internal_cognitive_tasks"))
        external_generation = _module_payload_data(module_payloads.get("q8_external_task_generation"))
        external_llm_output = _as_dict(external_generation.get("q8_external_llm_output"))
        if external_llm_output:
            _set_result("q8_external_llm_output", external_llm_output)
            _set_context("q8_external_llm_output", external_llm_output)
            _set_result("q8_external_execution_tasks", external_llm_output.get("external_execution_tasks"))
            _set_context("q8_external_execution_tasks", external_llm_output.get("external_execution_tasks"))
    elif question_id == "q9":
        snapshot = _module_payload_data(module_payloads.get("q9_q1_q8_validation"))
        _set_context("q9_q1_q8_snapshot", snapshot.get("q9_q1_q8_snapshot") or snapshot)
        self_model = _module_payload_data(module_payloads.get("q9_self_model_source_validation"))
        _set_context("q9_self_model", self_model.get("q9_self_model") or self_model)
        budget = _module_payload_data(module_payloads.get("q9_reasoning_budget_source_validation"))
        _set_context("q9_reasoning_budget", budget.get("q9_reasoning_budget") or budget)
        posture_baseline = _module_payload_data(module_payloads.get("q9_posture_baseline_projection"))
        _set_result("q9_posture_baseline", posture_baseline)
        posture = _module_payload_data(module_payloads.get("q9_posture_control_projection"))
        if posture:
            _set_result("q9_action_posture_profile", posture)
            action_plan = posture.get("action_plan") if isinstance(posture.get("action_plan"), dict) else posture
            _set_result("action_plan", action_plan)
            _set_result("q9_action_plan", posture.get("q9_action_plan") or action_plan)
            for key in ("evaluation_profile", "evolution_profile", "escalation_profile"):
                _set_result(key, posture.get(key))

    return merged_context, merged_result


def _build_flat_upstream_context(
    question_id: str,
    snapshot_map: dict[str, dict[str, Optional[Any]]],
) -> dict[str, Any]:
    question_no = _question_number(question_id)
    if question_no is None or question_no <= 1 or not snapshot_map:
        return {}

    merged: dict[str, Any] = {}
    for upstream_no in range(1, question_no):
        upstream_id = f"q{upstream_no}"
        snapshot = snapshot_map.get(upstream_id)
        if not isinstance(snapshot, dict):
            continue
        merged.update(_merge_snapshot_payload(snapshot))
    return merged


def _build_question_dependency_snapshot(
    snapshot_map: dict[str, dict[str, Optional[Any]]],
    *,
    upto_question_id: str,
) -> dict[str, Any]:
    if not snapshot_map:
        return {}

    ordered_ids = [f"q{i}" for i in range(1, 10)]
    if upto_question_id not in ordered_ids:
        return {}

    result: dict[str, Any] = {}
    max_index = ordered_ids.index(upto_question_id)
    for question_id in ordered_ids[: max_index + 1]:
        snapshot = snapshot_map.get(question_id)
        if not isinstance(snapshot, dict):
            continue
        result_payload = _as_dict(snapshot.get("result"))
        context_updates = _as_dict(snapshot.get("context_updates"))

        if question_id == "q1":
            value = {}
            domain = context_updates.get("workspace_domain_inference") or result_payload.get("workspace_domain_inference")
            uncertainty = context_updates.get("q1_uncertainty_profile") or result_payload.get("q1_uncertainty_profile")
            if isinstance(domain, dict) and domain:
                value.update(deepcopy(domain))
            if isinstance(uncertainty, dict) and uncertainty:
                value["q1_uncertainty_profile"] = deepcopy(uncertainty)
        elif question_id == "q2":
            value = context_updates.get("q2_asset_inventory") or result_payload.get("asset_inventory") or {}
        elif question_id == "q3":
            q3_result = result_payload.get("Q3InferenceResult") if isinstance(result_payload.get("Q3InferenceResult"), dict) else {}
            value = context_updates.get("q3_role_profile") or q3_result.get("RoleProfile") or {}
        elif question_id == "q4":
            value = context_updates.get("q4_capability_boundary_profile") or result_payload.get("capability_boundary_profile") or {}
        elif question_id == "q5":
            value = (
                context_updates.get("q5_authorization_boundary_profile")
                or context_updates.get("q5_permission_boundary")
                or result_payload.get("authorization_boundary_profile")
                or {}
            )
        elif question_id == "q6":
            value = (
                context_updates.get("q6_cost_impact_profile")
                or result_payload.get("CostImpactProfile")
                or result_payload.get("cost_impact_profile")
                or context_updates.get("q6_consequence_assessment")
                or result_payload.get("ConsequenceAssessment")
                or result_payload.get("consequence_assessment")
                or context_updates.get("q6_forbidden_zone_profile")
                or result_payload.get("forbidden_zone_profile")
                or {}
            )
        elif question_id == "q7":
            value = {}
            profile = (
                context_updates.get("q7_red_line_assessment")
                or context_updates.get("red_line_assessment")
                or result_payload.get("red_line_assessment")
            )
            if isinstance(profile, dict) and profile:
                value.update(deepcopy(profile))
            profile_body = _unwrap_q7_red_line_assessment(profile)
            constraints = context_updates.get("q7_non_bypassable_constraints") or profile_body.get("non_bypassable_constraints")
            if constraints not in (None, "", [], {}):
                value["non_bypassable_constraints"] = deepcopy(constraints)
        elif question_id == "q8":
            value = context_updates.get("q8_objective_profile") or result_payload.get("objective_profile") or {}
        else:
            value = {}

        if isinstance(value, dict) and value:
            result[question_id] = deepcopy(value)

    summaries: dict[str, Any] = {}
    for question_id in ordered_ids[: max_index + 1]:
        snapshot = snapshot_map.get(question_id)
        if not isinstance(snapshot, dict):
            continue
        summary_map = _as_dict(snapshot.get("context_updates")).get("nine_questions")
        if isinstance(summary_map, dict):
            summaries.update({str(k): v for k, v in summary_map.items() if str(k).strip()})
    if summaries:
        result["summaries"] = summaries

    return result


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _coerce_meaningful_string_list(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        for item in _coerce_string_list(value):
            if item.lower() in {"n/a", "na", "none", "unknown", "null"}:
                continue
            merged.append(item)
    return list(dict.fromkeys(entry for entry in merged if entry))


def _dependency_snapshot_has_signal(snapshot: Any) -> bool:
    if not isinstance(snapshot, dict):
        return False
    for value in snapshot.values():
        if isinstance(value, dict):
            if any(item not in (None, "", [], {}) for item in value.values()):
                return True
        elif value not in (None, "", [], {}):
            return True
    return False


def _derive_q5_actionable_space(context_updates: dict[str, Any]) -> list[str]:
    q4_profile = _as_dict(context_updates.get("q4_capability_boundary_profile"))
    q5_profile = _as_dict(context_updates.get("q5_authorization_boundary_profile"))
    permission_boundary = _as_dict(context_updates.get("q5_permission_boundary"))
    baseline = _as_dict(context_updates.get("q5_authorization_baseline"))
    merged = (
        _coerce_string_list(context_updates.get("actionable_space"))
        + _coerce_string_list(q4_profile.get("actionable_space"))
        + _coerce_string_list(q5_profile.get("allowed_action_space"))
        + _coerce_string_list(permission_boundary.get("authorized_actions"))
        + _coerce_string_list(permission_boundary.get("conditional_actions"))
        + _coerce_string_list(permission_boundary.get("unauthorized_actions"))
        + _coerce_string_list(baseline.get("allowed_action_space"))
    )
    seen: set[str] = set()
    return [item for item in merged if item and not (item in seen or seen.add(item))]


def _derive_q7_projection_fields(context_updates: dict[str, Any]) -> dict[str, Any]:
    q5_profile = _as_dict(context_updates.get("q5_authorization_boundary_profile"))
    q7_assessment = _unwrap_q7_red_line_assessment(context_updates.get("q7_red_line_assessment") or context_updates.get("red_line_assessment"))
    q7_baseline = _as_dict(context_updates.get("q7_red_line_baseline"))

    return {
        "q7_current_red_line_hits": _coerce_string_list(
            context_updates.get("q7_current_red_line_hits")
            or context_updates.get("q7_current_redline_hits")
            or q7_assessment.get("current_red_line_hits")
            or q7_assessment.get("current_redline_hits")
        ),
        "q7_rejected_operation_records": _coerce_string_list(
            context_updates.get("q7_rejected_operation_records")
            or context_updates.get("q7_rejected_operations_log")
            or q7_assessment.get("rejected_operation_records")
            or q7_assessment.get("rejected_operations_log")
            or q7_baseline.get("safety_rejection_history")
        ),
        "q7_ban_source_explanations": _coerce_string_list(
            context_updates.get("q7_ban_source_explanations")
            or context_updates.get("q7_constraint_sources_explanation")
            or q7_assessment.get("ban_source_explanations")
            or q7_assessment.get("constraint_sources_explanation")
            or q7_baseline.get("ban_source_explanations")
        ),
        "q7_non_bypassable_constraints": _coerce_string_list(
            context_updates.get("q7_non_bypassable_constraints")
            or q7_assessment.get("non_bypassable_constraints")
            or q7_baseline.get("non_bypassable_constraints")
        ),
        "q7_question_driver_refs": _coerce_string_list(
            context_updates.get("q7_question_driver_refs")
            or q7_assessment.get("question_driver_refs")
            or q7_baseline.get("question_driver_refs")
        ),
        "q7_absolute_red_lines": _coerce_string_list(
            context_updates.get("q7_absolute_red_lines")
            or q7_assessment.get("non_bypassable_constraints")
            or q7_baseline.get("non_bypassable_constraints")
            or q5_profile.get("forbidden_action_space")
        ),
    }


def _normalize_question_projection_context(
    question_id: str,
    merged: dict[str, Any],
    snapshot_map: dict[str, dict[str, Optional[Any]]],
) -> dict[str, Any]:
    normalized = deepcopy(merged)

    if question_id == "q5" and normalized.get("actionable_space") in (None, "", [], {}):
        actionable_space = _derive_q5_actionable_space(normalized)
        if actionable_space:
            normalized["actionable_space"] = actionable_space

    if question_id == "q7":
        for key, value in _derive_q7_projection_fields(normalized).items():
            if normalized.get(key) in (None, "", [], {}):
                normalized[key] = deepcopy(value)

    if question_id == "q8" and normalized.get("q1_q7_snapshot") in (None, "", [], {}):
        dependency_snapshot = _build_question_dependency_snapshot(snapshot_map, upto_question_id="q7")
        if dependency_snapshot:
            normalized["q1_q7_snapshot"] = dependency_snapshot
    elif question_id == "q8":
        dependency_snapshot = _build_question_dependency_snapshot(snapshot_map, upto_question_id="q7")
        if dependency_snapshot and not _dependency_snapshot_has_signal(normalized.get("q1_q7_snapshot")):
            normalized["q1_q7_snapshot"] = dependency_snapshot

    if question_id == "q9":
        dependency_snapshot = _build_question_dependency_snapshot(snapshot_map, upto_question_id="q8")
        if normalized.get("q1_q8_snapshot") in (None, "", [], {}) and dependency_snapshot:
            normalized["q1_q8_snapshot"] = deepcopy(dependency_snapshot)
        if normalized.get("q1_q8") in (None, "", [], {}) and dependency_snapshot:
            normalized["q1_q8"] = deepcopy(dependency_snapshot)
        if dependency_snapshot and not _dependency_snapshot_has_signal(normalized.get("q1_q8_snapshot")):
            normalized["q1_q8_snapshot"] = deepcopy(dependency_snapshot)
        if dependency_snapshot and not _dependency_snapshot_has_signal(normalized.get("q1_q8")):
            normalized["q1_q8"] = deepcopy(dependency_snapshot)

    return normalized


def _coalesce_q2_upstream_q1_context(
    merged: dict[str, Any],
    snapshot_map: dict[str, dict[str, Optional[Any]]],
) -> dict[str, Any]:
    if not snapshot_map:
        return merged

    q1_snapshot = snapshot_map.get("q1")
    if not isinstance(q1_snapshot, dict):
        return merged

    q1_payload = _merge_snapshot_payload(q1_snapshot)
    if not q1_payload:
        return merged

    normalized = deepcopy(merged)

    current_inference = _as_dict(normalized.get("workspace_domain_inference"))
    upstream_inference = _as_dict(q1_payload.get("workspace_domain_inference"))
    current_scene_model = _as_dict(normalized.get("q1_scene_model"))
    upstream_scene_model = _as_dict(q1_payload.get("q1_scene_model"))
    current_uncertainty = _as_dict(normalized.get("q1_uncertainty_profile"))
    upstream_uncertainty = _as_dict(q1_payload.get("q1_uncertainty_profile"))

    current_primary = str(current_inference.get("primary_domain") or current_scene_model.get("primary_domain") or "").strip().lower()
    upstream_primary = str(upstream_inference.get("primary_domain") or upstream_scene_model.get("primary_domain") or "").strip().lower()

    q1_is_degraded = current_primary in {"", "unknown", "none", "n/a", "na", "null"}
    upstream_has_signal = upstream_primary not in {"", "unknown", "none", "n/a", "na", "null"}

    if q1_is_degraded and upstream_has_signal:
        if upstream_inference:
            normalized["workspace_domain_inference"] = deepcopy(upstream_inference)
        if upstream_scene_model:
            normalized["q1_scene_model"] = deepcopy(upstream_scene_model)
        if upstream_uncertainty:
            normalized["q1_uncertainty_profile"] = deepcopy(upstream_uncertainty)
        return normalized

    if normalized.get("q1_scene_model") in (None, "", [], {}) and upstream_scene_model:
        normalized["q1_scene_model"] = deepcopy(upstream_scene_model)
    if normalized.get("q1_uncertainty_profile") in (None, "", [], {}) and upstream_uncertainty:
        normalized["q1_uncertainty_profile"] = deepcopy(upstream_uncertainty)

    return normalized


def _effective_context_updates(
    question_id: str,
    snapshot: dict[str, Any],
    snapshot_map: dict[str, dict[str, Optional[Any]]] = None,
) -> dict[str, Any]:
    context_updates = _as_dict(snapshot.get("context_updates"))
    execution_context = _as_dict(snapshot.get("execution_context"))
    result_payload = _as_dict(snapshot.get("result"))
    execution_result = _as_dict(snapshot.get("execution_result"))
    result_context_updates = _as_dict(result_payload.get("context_updates"))
    execution_result_context_updates = _as_dict(execution_result.get("context_updates"))

    merged = {}
    merged.update(execution_context)
    merged.update(result_context_updates)
    merged.update(execution_result_context_updates)
    merged.update(context_updates)

    if snapshot_map:
        merged = _merge_missing_fields(merged, _build_flat_upstream_context(question_id, snapshot_map))
        merged = _normalize_question_projection_context(question_id, merged, snapshot_map)
        if question_id == "q2":
            merged = _coalesce_q2_upstream_q1_context(merged, snapshot_map)

    return merged


def _has_q1_inference_payload(value: dict[str, Any]) -> bool:
    return any(
        _first_non_empty_str(value.get(key))
        for key in ("primary_domain", "reasoning_summary", "suggested_first_step", "host_runtime_type")
    )


def _first_non_empty_str(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _build_q1_source_summary(
    *,
    evidence: dict[str, Any],
    inference: dict[str, Any],
    error_message: Optional[str],
    diagnosis: dict[str, Optional[Any]] = None,
) -> dict[str, Any]:
    has_runtime = bool(evidence.get("physical_and_environment"))
    has_structure = bool(evidence.get("workspace_structure"))
    has_sampling = bool(evidence.get("workspace_content_sampling"))
    has_inference = _has_q1_inference_payload(inference)
    diagnosis = diagnosis or {}

    if has_inference:
        domain_inference_source = "current_inference_result"
    elif error_message:
        domain_inference_source = "unavailable_due_to_failure"
    else:
        domain_inference_source = "missing"

    snapshot_fallback_used = diagnosis.get("snapshot_fallback_used", False)
    overall_authenticity = diagnosis.get("overall_authenticity", "unknown")
    functional_chain_status = diagnosis.get("functional_chain_status", "unavailable")
    environment_service_status = diagnosis.get("environment_service_status", "unavailable")
    producer_status = diagnosis.get("producer_status", {}) if isinstance(diagnosis, dict) else {}

    if error_message:
        display_origin_explanation = (
            "当前页面只展示本次仍可确认的 Q1 证据；未沿用旧结果，本次推断结论不可用。"
        )
    else:
        display_origin_explanation = "本次 Q1 来自真实环境链推理。"

    return {
        "physical_and_environment": "runtime_telemetry" if has_runtime else "missing",
        "workspace_structure": "workspace_structure_analysis" if has_structure else "missing",
        "workspace_content_sampling": "workspace_content_samples" if has_sampling else "missing",
        "domain_inference": domain_inference_source,
        "reused_previous_success": False,
        "snapshot_fallback_used": snapshot_fallback_used,
        "overall_authenticity": overall_authenticity,
        "functional_chain_status": functional_chain_status,
        "environment_service_status": environment_service_status,
        "workspace_root": producer_status.get("workspace_root", "unknown"),
        "workspace_access_policy": producer_status.get("workspace_access_policy", "unknown"),
        "allowed_workspace_roots": producer_status.get("allowed_workspace_roots", []),
        "structure_source": producer_status.get("structure_source", "unknown"),
        "samples_source": producer_status.get("samples_source", "unknown"),
        "display_origin_explanation": display_origin_explanation,
    }


def _build_q2_source_summary(
    *,
    evidence: dict[str, Any],
    inference: dict[str, Any],
    error_message: Optional[str],
) -> dict[str, Any]:
    has_q1 = bool(evidence.get("q1_summary"))
    has_identity_kernel = bool(evidence.get("identity_kernel"))
    has_inference = bool(inference)
    role_inference = (
        "current_inference_result"
        if has_inference
        else "unavailable_due_to_failure"
        if error_message
        else "missing"
    )
    display_origin_explanation = (
        "当前页面只展示本次仍可确认的 Q2 证据；未沿用旧结果，本次角色推断结论不可用。"
        if error_message
        else "当前页面展示的是本次 Q2 快照结果；未沿用旧结果。"
    )
    return {
        "q1_summary": "q1_context_projection" if has_q1 else "missing",
        "identity_kernel": "identity_kernel_snapshot" if has_identity_kernel else "missing",
        "manual_intervention": "missing",
        "role_inference": role_inference,
        "reused_previous_success": False,
        "display_origin_explanation": display_origin_explanation,
    }


def _safe_extract_evidence(question_id: str, context_updates: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    if question_id == "q3":
        handler = QUESTION_EXTRACTORS.get(question_id)
        if handler:
            q3_context = deepcopy(context_updates)
            llm_trace_payload = _as_dict(snapshot.get("llm_trace_payload"))
            context_llm_trace_payload = _as_dict(context_updates.get("llm_trace_payload"))
            if llm_trace_payload and q3_context.get("llm_trace_payload") in (None, "", [], {}):
                q3_context["llm_trace_payload"] = llm_trace_payload
            elif context_llm_trace_payload:
                q3_context["llm_trace_payload"] = context_llm_trace_payload
            try:
                evidence = _as_dict(handler["evidence"](q3_context))
                if evidence:
                    return evidence
            except Exception:
                logger.exception("Failed to extract Q3 preprocessed evidence from role-scoped context")
    direct = _as_dict(snapshot.get("preprocessed_evidence"))
    if direct:
        if question_id == "q2" and not _has_q2_asset_inventory_rows(direct.get("asset_inventory")):
            handler = QUESTION_EXTRACTORS.get(question_id)
            if handler:
                try:
                    return _merge_q2_asset_projection(direct, _as_dict(handler["evidence"](context_updates)))
                except Exception:
                    logger.exception("Failed to backfill Q2 preprocessed evidence from context updates")
        return direct
    handler = QUESTION_EXTRACTORS.get(question_id)
    if not handler:
        return {}
    try:
        return _as_dict(handler["evidence"](context_updates))
    except Exception:
        logger.exception("Failed to extract preprocessed evidence for question %s", question_id)
        return {}


def _safe_extract_inference(question_id: str, result_payload: dict[str, Any], context_updates: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    if question_id == "q3":
        handler = QUESTION_EXTRACTORS.get(question_id)
        if handler:
            current_payload = deepcopy(result_payload)
            current_payload["context_updates"] = deepcopy(context_updates)
            try:
                inference = _as_dict(handler["result"](current_payload))
                if inference:
                    return inference
                inference = _as_dict(handler["result"](context_updates))
                if inference:
                    return inference
            except Exception:
                logger.exception("Failed to extract current Q3 inference result")
    direct = _as_dict(snapshot.get("inference_result"))
    if direct:
        if question_id == "q2" and not _has_q2_asset_inventory_rows(direct.get("asset_inventory")):
            handler = QUESTION_EXTRACTORS.get(question_id)
            if handler:
                try:
                    return _merge_q2_asset_projection(direct, _as_dict(handler["result"](context_updates)))
                except Exception:
                    logger.exception("Failed to backfill Q2 inference result from context updates")
        return direct
    execution_result = _as_dict(snapshot.get("execution_result"))
    if question_id == "q1" and execution_result and _has_q1_inference_payload(execution_result):
        return execution_result
    handler = QUESTION_EXTRACTORS.get(question_id)
    if not handler:
        return {}
    try:
        inference = _as_dict(handler["result"](result_payload))
        if inference:
            return inference
        inference = _as_dict(handler["result"](execution_result))
        if inference:
            return inference
        return _as_dict(handler["result"](context_updates))
    except Exception:
        logger.exception("Failed to extract inference result for question %s", question_id)
        return {}


def _module_payload(
    module_id: str,
    data: Any,
    *,
    timestamp: str,
    status: Optional[str] = None,
    error: Optional[str] = None,
) -> dict[str, Any]:
    normalized = deepcopy(data)
    
    # 1. Check for explicit status in the data payload (Module Result Contract)
    explicit_status = None
    if isinstance(normalized, dict):
        # We look for 'status' if it's a structured module result
        # ensuring it's one of the known status strings
        ds = normalized.get("status")
        if ds in {"ready", "failed", "degraded", "missing", "skipped"}:
            explicit_status = ds
            # Extract error if present in module result
            if not error and "error" in normalized:
                error = normalized.get("error")

    is_present = normalized not in ({}, [], None, "")
    return {
        "module_id": module_id,
        "status": status or explicit_status or ("ready" if is_present else "missing"),
        "updated_at": timestamp,
        "error": error,
        "data": normalized,
    }


def _extract_execution_diagnosis(question_id: str, context_updates: dict[str, Any]) -> dict[str, Optional[Any]]:
    diagnosis = context_updates.get(f"{question_id}_execution_diagnosis")
    if isinstance(diagnosis, dict):
        return deepcopy(diagnosis)
    return None


def _build_diagnostic_modules(
    diagnosis: dict[str, Any],
    *,
    timestamp: str,
) -> dict[str, dict[str, Any]]:
    module_payloads: dict[str, dict[str, Any]] = {}
    for item in diagnosis.get("module_runs", []):
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("module_id") or "").strip()
        if not module_id:
            continue
        module_payloads[module_id] = {
            "module_id": module_id,
            "status": str(item.get("status") or "missing"),
            "updated_at": str(item.get("finished_at") or item.get("started_at") or timestamp),
            "error": _first_non_empty_str(item.get("error_message"), item.get("error_code")),
            "data": deepcopy(item.get("data")) if isinstance(item.get("data"), dict) else deepcopy(item),
        }
    return module_payloads


def _split_modules(
    question_id: str,
    evidence: dict[str, Any],
    inference: dict[str, Any],
    raw_snapshot: dict[str, Any],
    *,
    timestamp: str,
    question_error: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    diagnosis = _extract_execution_diagnosis(question_id, raw_snapshot.get("context_updates", {}))
    if diagnosis and isinstance(diagnosis.get("module_runs"), list) and diagnosis.get("module_runs"):
        module_payloads = _build_diagnostic_modules(diagnosis, timestamp=timestamp)
        if module_payloads:
            return module_payloads
    if question_id == "q1":
        diagnosis = raw_snapshot.get("context_updates", {}).get("q1_execution_diagnosis", {})
        dep_check = diagnosis.get("dependency_check", {})
        _chain_status = diagnosis.get("functional_chain_status", "unavailable")
        _env_svc_status = diagnosis.get("environment_service_status", "unavailable")

        _chain_module_status = (
            "ready" if _chain_status == "completed"
            else "partial_failed" if _chain_status == "partial"
            else "failed" if _chain_status == "failed"
            else "missing"
        )
        _env_svc_module_status = (
            "ready" if _env_svc_status == "completed"
            else "failed" if _env_svc_status == "failed"
            else "missing"
        )
        _dep_check_module_status = (
            "ready" if dep_check.get("plugin_service_present")
            else "missing" if not dep_check
            else "failed"
        )
        _state_write_data = {
            "overall_authenticity": diagnosis.get("overall_authenticity"),
            "snapshot_fallback_used": diagnosis.get("snapshot_fallback_used", False),
            "producer_status": diagnosis.get("producer_status", {}),
        }
        _state_write_status = (
            "ready" if diagnosis
            else "missing"
        )

        q1_payloads: dict[str, dict[str, Any]] = {
            "dependency_check": _module_payload(
                "dependency_check", dep_check, timestamp=timestamp,
                status=_dep_check_module_status,
            ),
            "functional_plugin_chain": _module_payload(
                "functional_plugin_chain",
                {
                    "status": _chain_status,
                    "error": diagnosis.get("functional_chain_error"),
                    "plugin_runs": diagnosis.get("plugin_runs", []),
                    "snapshot_fallback_used": diagnosis.get("snapshot_fallback_used", False),
                },
                timestamp=timestamp,
                status=_chain_module_status,
            ),
            "environment_service": _module_payload(
                "environment_service",
                {"status": _env_svc_status},
                timestamp=timestamp,
                status=_env_svc_module_status,
            ),
            "environment_scan": _module_payload(
                "environment_scan", evidence.get("physical_and_environment", {}),
                timestamp=timestamp,
            ),
            "workspace_structure_scan": _module_payload(
                "workspace_structure_scan", evidence.get("workspace_structure", {}),
                timestamp=timestamp,
            ),
            "content_sampling": _module_payload(
                "content_sampling", evidence.get("workspace_content_sampling", {}),
                timestamp=timestamp,
            ),
            "uncertainty_projection": _module_payload(
                "uncertainty_projection",
                raw_snapshot.get("context_updates", {}).get("q1_uncertainty_profile", {}),
                timestamp=timestamp,
            ),
            "domain_inference": _module_payload(
                "domain_inference", inference, timestamp=timestamp,
            ),
            "state_write": _module_payload(
                "state_write", _state_write_data, timestamp=timestamp,
                status=_state_write_status,
            ),
        }
        if question_error:
            for _mid in ("domain_inference", "uncertainty_projection", "state_write"):
                _p = q1_payloads.get(_mid)
                if isinstance(_p, dict) and _p.get("status") in ("missing", "degraded"):
                    _p["status"] = "failed"
                    _p["error"] = question_error
        return q1_payloads
    elif question_id == "q2":
        context_updates = raw_snapshot.get("context_updates", {})
        mapping = {
            "identity_kernel_builder": evidence.get("identity_kernel", {}),
            "role_candidates": inference.get("role_profile", {}),
            "risk_preference_projection": context_updates.get("q2_risk_preference", {}),
            "mission_continuity_projection": context_updates.get("mission_continuity_projection") or inference.get("mission_boundary", {}),
            "role_inference": inference,
        }
    elif question_id == "q3":
        tools_agents = evidence.get("tools_agents", {})
        mapping = {
            "workspace_permission_inventory": evidence.get("workspace_permission", {}),
            "cognitive_tools_inventory": {
                "cognitive_tools": tools_agents.get("cognitive_tools", []),
                "cognitive_tool_rows": tools_agents.get("cognitive_tool_rows", []),
            },
            "execution_tools_inventory": {
                "execution_tools": tools_agents.get("execution_tools", []),
                "execution_tool_rows": tools_agents.get("execution_tool_rows", []),
            },
            "connected_agents_inventory": {
                "connected_agents": tools_agents.get("connected_agents", []),
                "connected_agent_rows": tools_agents.get("connected_agent_rows", []),
            },
            "mcp_inventory": {"mcp_servers": tools_agents.get("mcp_servers", [])},
            "cli_inventory": {"cli_tools": tools_agents.get("cli_tools", [])},
            "memory_strategy_inventory": evidence.get("memory_strategy", {}),
            "resource_sufficiency_inference": inference,
        }
    elif question_id == "q4":
        mapping = {
            "q1_context_projection": evidence.get("q1_context", {}),
            "q2_context_projection": evidence.get("q2_context", {}),
            "q3_inventory_projection": evidence.get("q3_inventory", {}),
            "capability_limits_inference": {"capability_upper_limits": inference.get("capability_upper_limits", [])},
            "actionable_space_inference": {"actionable_space": inference.get("actionable_space", [])},
            "strategy_inference": {"executable_strategies": inference.get("executable_strategies", [])},
        }
    elif question_id == "q5":
        mapping = {
            "actionable_space_projection": {"actionable_space": evidence.get("actionable_space", [])},
            "contact_policy_projection": {"contact_policy": evidence.get("contact_policy", [])},
            "tenant_boundary_projection": {"tenant_boundaries": evidence.get("tenant_boundaries", [])},
            "agent_trust_projection": {"agent_trust_status": evidence.get("agent_trust_status", {})},
            "authorization_inference": {
                "execution_tier": inference.get("execution_tier"),
                "interaction_scope": inference.get("interaction_scope"),
                "requires_human_confirmation": inference.get("requires_human_confirmation"),
                "requires_cloud_audit": inference.get("requires_cloud_audit"),
                "allowed_delegation_targets": inference.get("allowed_delegation_targets", []),
            },
            "compliance_inference": {
                "explicitly_forbidden_actions": inference.get("explicitly_forbidden_actions", []),
                "compliance_risks": inference.get("compliance_risks", []),
            },
        }
    elif question_id == "q6":
        consequence_raw = inference.get("ConsequenceAssessment") or inference.get("consequence_assessment")
        cost_raw = inference.get("CostImpactProfile") or inference.get("cost_impact_profile")
        consequence = consequence_raw if isinstance(consequence_raw, dict) else {}
        cost_profile = cost_raw if isinstance(cost_raw, dict) else {}
        mapping = {
            "authorization_boundary_projection": {"authorization_boundaries": evidence.get("authorization_boundaries", [])},
            "non_bypassable_constraints_projection": {"non_bypassable_constraints": evidence.get("non_bypassable_constraints", [])},
            "historical_strategy_patch_projection": {"historical_strategy_patches": evidence.get("historical_strategy_patches", [])},
            "consequence_assessment_inference": {
                "action_under_review": consequence.get("action_under_review"),
                "immediate_consequences": consequence.get("immediate_consequences", []),
                "downstream_consequences": consequence.get("downstream_consequences", []),
                "consequence_severity": consequence.get("consequence_severity"),
                "reversibility": consequence.get("reversibility"),
            },
            "cost_impact_inference": {
                "CostImpactProfile": cost_profile,
            },
            "mitigation_requirement_inference": {
                "mitigation_requirements": cost_profile.get("mitigation_requirements", []),
                "stop_conditions": cost_profile.get("stop_conditions", []),
            },
        }
    elif question_id == "q7":
        mapping = {
            "red_line_baseline_projection": {
                "identity_kernel_constraints": evidence.get("identity_kernel_constraints", []),
                "authorization_boundary_constraints": evidence.get("authorization_boundary_constraints", []),
                "safety_rejection_history": evidence.get("safety_rejection_history", []),
                "procedural_memory_constraints": evidence.get("procedural_memory_constraints", []),
                "non_bypassable_constraints": evidence.get("non_bypassable_constraints", []),
            },
            "red_line_assessment_inference": {
                "current_red_line_hits": inference.get("current_red_line_hits", []),
                "rejected_operation_records": inference.get("rejected_operation_records", []),
                "ban_source_explanations": inference.get("ban_source_explanations", []),
                "non_bypassable_constraints": inference.get("non_bypassable_constraints", []),
                "question_driver_refs": inference.get("question_driver_refs", []),
            },
        }
    elif question_id == "q8":
        runtime_state = evidence.get("runtime_state", {})
        mapping = {
            "aggregated_context_projection": evidence.get("aggregated_context", {}),
            "persistent_task_state_projection": {"persistent_task_state": runtime_state.get("persistent_task_state", [])},
            "cognitive_agenda_projection": {"cognitive_agenda": runtime_state.get("cognitive_agenda", [])},
            "objective_inference": {"objective_profile": inference.get("objective_profile", {})},
            "task_queue_inference": {"task_queue": inference.get("task_queue", {})},
            "priority_order_inference": {
                "priority_order": inference.get("objective_profile", {}).get("priority_order", []),
            },
        }
    elif question_id == "q9":
        mapping = {
            "cognitive_snapshot_projection": evidence.get("cognitive_snapshot", {}),
            "self_model_projection": evidence.get("self_model", {}),
            "reasoning_budget_projection": evidence.get("reasoning_budget", {}),
            "action_posture_inference": inference,
            "risk_tolerance_inference": {"risk_tolerance": inference.get("risk_tolerance")},
            "confirmation_strategy_inference": {"confirmation_strategy": inference.get("confirmation_strategy")},
            "evolution_direction_inference": {"evolution_direction": inference.get("evolution_direction")},
        }
    else:
        mapping = {}

    module_ids = QUESTION_MODULE_IDS.get(question_id, [])
    module_payloads = {
        module_id: _module_payload(module_id, mapping.get(module_id, {}), timestamp=timestamp)
        for module_id in module_ids
    }
    if question_id == "q1" and question_error:
        domain_inference = module_payloads.get("domain_inference")
        if isinstance(domain_inference, dict) and domain_inference.get("status") == "missing":
            domain_inference["status"] = "failed"
            domain_inference["error"] = question_error
        uncertainty_projection = module_payloads.get("uncertainty_projection")
        if isinstance(uncertainty_projection, dict) and uncertainty_projection.get("status") == "missing":
            uncertainty_projection["status"] = "failed"
            uncertainty_projection["error"] = question_error
    if question_id == "q2" and question_error:
        role_inference = module_payloads.get("role_inference")
        if isinstance(role_inference, dict) and role_inference.get("status") == "missing":
            role_inference["status"] = "failed"
            role_inference["error"] = question_error
    return module_payloads


def build_question_record(
    question_id: str,
    snapshot: dict[str, Any],
    snapshot_map: dict[str, dict[str, Optional[Any]]] = None,
    *,
    module_payload_overrides: dict[str, Optional[Any]] = None,
    module_run_overrides: dict[str, Optional[Any]] = None,
) -> dict[str, Any]:
    timestamp = str(snapshot.get("timestamp") or datetime.now(timezone.utc).isoformat())
    context_updates = _effective_context_updates(question_id, snapshot, snapshot_map=snapshot_map)
    result_payload = _as_dict(snapshot.get("result"))
    context_updates, result_payload = _inject_module_outputs_into_projection(
        question_id,
        context_updates,
        result_payload,
        module_payload_overrides,
    )
    llm_trace_payload = _merge_llm_trace_payload(
        snapshot.get("llm_trace_payload"),
        context_updates.get("llm_trace_payload"),
    )
    execution_result = _as_dict(snapshot.get("execution_result"))
    evidence = _safe_extract_evidence(question_id, context_updates, snapshot)
    inference = _safe_extract_inference(question_id, result_payload, context_updates, snapshot)
    execution_diagnosis = _extract_execution_diagnosis(question_id, context_updates)
    if module_run_overrides:
        normalized_runs = [
            deepcopy(item)
            for _, item in sorted(module_run_overrides.items())
            if isinstance(item, dict)
        ]
        if execution_diagnosis is None:
            execution_diagnosis = {"module_runs": normalized_runs}
        else:
            execution_diagnosis["module_runs"] = normalized_runs
    error_message = _first_non_empty_str(
        snapshot.get("error"),
        result_payload.get("error"),
        execution_result.get("error_message"),
        execution_result.get("error"),
        _as_dict(llm_trace_payload).get("error_message"),
        _as_dict(llm_trace_payload).get("error"),
    )
    modules = _split_modules(
        question_id,
        evidence,
        inference,
        {
            **snapshot,
            "result": result_payload,
            "context_updates": context_updates,
        },
        timestamp=timestamp,
        question_error=error_message,
    )
    if module_payload_overrides:
        for module_id, payload in module_payload_overrides.items():
            if isinstance(payload, dict):
                modules[module_id] = deepcopy(payload)
    trace_payload = _as_dict(llm_trace_payload)
    module_statuses = {module_id: payload.get("status", "missing") for module_id, payload in modules.items()}
    execution_authenticity = (
        str(execution_diagnosis.get("authenticity_status") or "").strip().lower()
        if isinstance(execution_diagnosis, dict)
        else ""
    )
    unhealthy_module_statuses = {"failed", "missing", "partial", "partial_failed", "degraded", "abnormal"}
    has_unhealthy_module = any(
        str(status or "").strip().lower() in unhealthy_module_statuses
        for status in module_statuses.values()
    )
    # A previous failed snapshot may leave stale error text in the stored payload.
    # When current diagnosis and module statuses are fully healthy, do not surface stale errors.
    if error_message and execution_authenticity in {"completed", "ready"} and not has_unhealthy_module:
        error_message = None
    ready_count = sum(1 for status in module_statuses.values() if status == "ready")
    q1_diagnosis = context_updates.get("q1_execution_diagnosis") if question_id == "q1" else None
    if error_message:
        overall_status = "partial_failed" if ready_count > 0 else "failed"
    elif execution_diagnosis:
        overall_status = str(execution_diagnosis.get("authenticity_status") or "partial")
    elif question_id == "q1":
        snapshot_fallback_used = (q1_diagnosis or {}).get("snapshot_fallback_used", False)
        if snapshot_fallback_used and ready_count > 0:
            overall_status = "degraded"
        elif ready_count == len(modules):
            overall_status = "ready"
        elif ready_count > 0:
            overall_status = "partial"
        else:
            overall_status = "missing"
    else:
        overall_status = "ready" if ready_count == len(modules) else "partial" if ready_count > 0 else "missing"

    source_summary = (
        _build_q1_source_summary(
            evidence=evidence,
            inference=inference,
            error_message=error_message,
            diagnosis=q1_diagnosis,
        )
        if question_id == "q1"
        else _build_q2_source_summary(
            evidence=evidence,
            inference=inference,
            error_message=error_message,
        )
        if question_id == "q2"
        else None
    )

    return {
        "composed_schema_version": COMPOSED_RECORD_SCHEMA_VERSION,
        "status": {
            "question_id": question_id,
            "status": overall_status,
            "updated_at": timestamp,
            "composed_schema_version": COMPOSED_RECORD_SCHEMA_VERSION,
            "module_statuses": module_statuses,
            "error_message": error_message,
            "source_summary": source_summary,
            **({"reused_previous_success": False} if question_id == "q2" else {}),
            **({"diagnosis": q1_diagnosis} if q1_diagnosis else {}),
        },
        "modules": modules,
        **({"plugin_runs": (q1_diagnosis or {}).get("plugin_runs", [])} if question_id == "q1" else {}),
        **({"plugin_runs": execution_diagnosis.get("plugin_runs", [])} if execution_diagnosis and question_id != "q1" else {}),
        **({"upstream_dependencies": execution_diagnosis.get("upstream_dependencies", [])} if execution_diagnosis and question_id != "q1" else {}),
        **({"recovery_plan": execution_diagnosis.get("recovery_plan", {})} if execution_diagnosis and question_id != "q1" else {}),
        **({"execution_diagnosis": execution_diagnosis} if execution_diagnosis and question_id != "q1" else {}),
        **({"authenticity_status": overall_status} if execution_diagnosis and question_id != "q1" else {}),
        "composed": {
            "summary": {
                "question_id": question_id,
                "summary": str(snapshot.get("summary") or ""),
                "confidence": float(snapshot.get("confidence") or 0.0),
                "timestamp": timestamp,
                "status": overall_status,
            },
            "evidence": evidence,
            "inference": inference,
            "trace": trace_payload,
            "raw": {
                "question_id": question_id,
                "tool_id": snapshot.get("tool_id"),
                "trace_id": snapshot.get("trace_id"),
                "timestamp": timestamp,
                "result": result_payload,
                "context_updates": context_updates,
                "execution_context": _as_dict(snapshot.get("execution_context")),
                "execution_result": execution_result,
                "llm_trace_payload": trace_payload,
            },
        },
    }
