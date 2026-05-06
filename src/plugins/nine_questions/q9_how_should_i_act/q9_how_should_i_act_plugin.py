from __future__ import annotations

import logging
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_llm_output_from_table as load_q2_llm_output_from_table,
)
from plugins.nine_questions.q1_where_am_i.llm_output_table import (
    load_llm_output_from_table as load_q1_llm_output_from_table,
)
from plugins.nine_questions.q3_role_inference.llm_output_table import (
    load_llm_output_from_table as load_q3_llm_output_from_table,
)
from plugins.nine_questions.q4_what_can_i_do.llm_output_table import (
    load_llm_output_from_table as load_q4_llm_output_from_table,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_output_table import (
    load_llm_output_from_table as load_q5_llm_output_from_table,
)
from plugins.nine_questions.q6_what_should_i_not_do.llm_output_table import (
    load_llm_output_from_table as load_q6_llm_output_from_table,
)
from plugins.nine_questions.q7_what_else_can_i_do.llm_output_table import (
    load_llm_output_from_table as load_q7_llm_output_from_table,
)
from plugins.nine_questions.q8_what_should_i_do_now.llm_output_table import (
    load_llm_output_from_table as load_q8_llm_output_from_table,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q9
from zentex.plugins.models import PluginLifecycleStatus
from plugins.nine_questions.q9_how_should_i_act.modules import (
    derive_posture_baseline,
    normalize_functional_postures,
    normalize_reasoning_budget,
    normalize_self_model,
    normalize_snapshot_dict,
)
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    build_question_dependency,
    fail_module_run,
    finish_module_run,
    persist_question_module_output,
    question_authenticity_judgment,
    start_module_run,
    build_caller_context,
    record_model_failed,
    require_model_provider,
    require_transcript_store,
)
from zentex.plugins.service import (
    execute_enabled_cognitive_plugin_functionals,
)
from plugins.nine_questions.q9_how_should_i_act.external_tasks import (
    run_q9_external_task_generation,
)
from plugins.nine_questions.q9_how_should_i_act.internal_tasks import (
    run_q9_internal_task_generation,
)

logger = logging.getLogger(__name__)


def _q9_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _q9_text(value: Any) -> str:
    return str(value or "").strip()


def _q9_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    result: list[Any] = []
    for item in value:
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            compact = {
                str(key): _q9_text(val)
                for key, val in item.items()
                if val not in (None, "", [], {})
            }
            if compact:
                result.append(compact)
        else:
            result.append(_q9_text(item))
    return result


def _q9_status(payload: dict[str, Any], key: str) -> str:
    diagnosis = _q9_dict(payload.get(key))
    return _q9_text(diagnosis.get("authenticity_status") or payload.get("status"))


def _build_q9_posture_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    q1 = _q9_dict(snapshot.get("q1"))
    q2 = _q9_dict(snapshot.get("q2"))
    q3 = _q9_dict(snapshot.get("q3"))
    q4 = _q9_dict(snapshot.get("q4"))
    q5 = _q9_dict(snapshot.get("q5"))
    q6 = _q9_dict(snapshot.get("q6"))
    q7 = _q9_dict(snapshot.get("q7"))
    q8 = _q9_dict(snapshot.get("q8"))

    q1_scene = _q9_dict(q1.get("q1_scene_model") or q1.get("workspace_domain_inference"))
    q2_internal_output = _q9_dict(q2.get("q2_internal_tool_asset_inventory"))
    q2_external_output = _q9_dict(q2.get("q2_external_tool_asset_inventory"))
    q2_cognitive_plugins = _q9_list(q2_internal_output.get("internal_cognitive_tools"))
    q2_functional_plugins = _q9_list(q2_internal_output.get("internal_functional_plugins"))
    q2_external_tools = _q9_list(q2_external_output.get("available_external_tools"))
    q2_external_agents = _q9_list(q2_external_output.get("external_agents"))
    q3_role = _q9_dict(q3.get("q3_role_profile") or q3.get("identity_kernel_snapshot"))
    q4_profile = _q9_dict(q4.get("q4_capability_boundary_profile") or q4.get("q4_capability_baseline"))
    q5_boundary = _q9_dict(q5.get("q5_authorization_boundary") or q5.get("authorization_boundary"))
    q5_boundary = _q9_dict(q5_boundary.get("AuthorizationBoundary") or q5_boundary)
    q5_profile = _q9_dict(q5.get("q5_authorization_boundary_profile") or q5.get("q5_authorization_baseline"))
    q5_convergence_guard = _q9_dict(q5.get("q5_objective_convergence_guard"))
    q6_profile = _q9_dict(
        q6.get("q6_consequence_inference")
        or q6.get("q6_cost_impact_profile")
        or q6.get("q6_consequence_assessment")
        or q6.get("q6_forbidden_zone_profile")
        or q6.get("q6_forbidden_zone_baseline")
    )
    q7_profile = _q9_dict(q7.get("q7_red_line_assessment") or q7.get("red_line_assessment") or q7)
    q8_result = _q9_dict(q8.get("q8_objective_and_queue") or q8)
    q8_objective = _q9_dict(q8_result.get("objective") or q8.get("q8_objective_profile"))
    q8_queue = _q9_dict(q8_result.get("task_queue") or q8.get("q8_task_queue"))
    q8_external_tasks = _q9_list(q8.get("q8_external_execution_tasks"))
    q8_internal_tasks = _q9_list(q8.get("q8_internal_cognitive_tasks"))

    return {
        "q1": {
            "status": _q9_status(q1, "q1_execution_diagnosis"),
            "environment_summary": _q9_text(q1.get("summary")),
            "primary_domain": _q9_text(q1_scene.get("primary_domain")),
            "uncertainty": _q9_dict(q1.get("q1_uncertainty_profile")),
        },
        "q2": {
            "status": "completed",
            "resource_status": "",
            "bottleneck_node": "",
            "missing_critical_assets": [],
            "internal_assets": q2_cognitive_plugins + q2_functional_plugins,
            "external_assets": q2_external_tools + q2_external_agents,
            "available_cognitive_tools": q2_cognitive_plugins,
            "cognitive_plugins": q2_cognitive_plugins,
            "internal_cognitive_plugins": q2_cognitive_plugins,
            "functional_plugins": q2_functional_plugins,
            "available_execution_tools": q2_external_tools,
            "external_agents": q2_external_agents,
        },
        "q3": {
            "status": _q9_status(q3, "q3_execution_diagnosis"),
            "identity_role": _q9_text(q3_role.get("identity_role")),
            "active_role": _q9_text(q3_role.get("active_role")),
            "inferred_reference_role": _q9_text(q3_role.get("inferred_reference_role")),
            "role_alignment_gap": _q9_text(q3_role.get("role_alignment_gap")),
            "task_role": _q9_text(q3_role.get("task_role")),
        },
        "q4": {
            "status": _q9_status(q4, "q4_execution_diagnosis"),
            "verified_capabilities": _q9_list(
                q4_profile.get("verified_capabilities") or q4.get("verified_capabilities"),
            ),
            "actionable_space": _q9_list(q4_profile.get("actionable_space")),
            "capability_upper_limits": _q9_list(q4_profile.get("capability_upper_limits")),
        },
        "q5": {
            "status": _q9_status(q5, "q5_execution_diagnosis"),
            "current_authorization_scope": _q9_text(q5_boundary.get("current_authorization_scope") or q5_profile.get("current_authorization_scope")),
            "organizational_boundaries": _q9_text(q5_boundary.get("organizational_boundaries") or q5_boundary.get("organizational_boundary") or q5_profile.get("organizational_boundaries")),
            "contact_policies": _q9_list(q5_boundary.get("contact_policies") or q5_boundary.get("communication_policy") or q5_profile.get("contact_policies")),
            "allowed_action_space": _q9_list(q5_profile.get("allowed_action_space") or q5_boundary.get("allowed_operations") or q5_boundary.get("allowed_actions")),
            "forbidden_action_space": _q9_list(q5_profile.get("forbidden_action_space") or q5_boundary.get("forbidden_operations") or q5_boundary.get("forbidden_actions")),
            "requires_escalation_actions": _q9_list(q5_profile.get("requires_escalation_actions")),
            "objective_scope": _q9_text(q5_convergence_guard.get("objective_scope")),
            "authorization_limited": bool(q5_convergence_guard.get("authorization_limited", False)),
        },
        "q6": {
            "status": _q9_status(q6, "q6_execution_diagnosis"),
            "absolute_red_lines": _q9_list(q6_profile.get("absolute_red_lines")),
            "performance_tradeoff_bans": _q9_list(q6_profile.get("performance_tradeoff_bans")),
            "prohibited_strategies": _q9_list(q6_profile.get("prohibited_strategies")),
        },
        "q7": {
            "status": _q9_status(q7, "q7_execution_diagnosis"),
            "current_red_line_hits": _q9_list(q7_profile.get("current_red_line_hits")),
            "rejected_operation_records": _q9_list(q7_profile.get("rejected_operation_records")),
            "non_bypassable_constraints": _q9_list(q7_profile.get("non_bypassable_constraints")),
        },
        "q8": {
            "status": _q9_status(q8, "q8_execution_diagnosis"),
            "current_mission": _q9_text(q8_objective.get("current_mission") or q8.get("summary")),
            "current_phase_tasks": _q9_list(q8_objective.get("current_phase_tasks")),
            "priority_order": _q9_list(q8_objective.get("priority_order")),
            "next_self_tasks": _q9_list(q8_queue.get("next_self_tasks")),
            "blocked_self_tasks": _q9_list(q8_queue.get("blocked_self_tasks")),
            "proactive_actions": _q9_list(q8_queue.get("proactive_actions")),
            "external_execution_tasks": q8_external_tasks,
            "internal_cognitive_tasks": q8_internal_tasks,
        },
    }


def _existing_q9_committed_result(context: dict[str, Any]) -> CognitiveToolResult | None:
    state = _q9_dict(context.get("nine_question_state"))
    snapshots = _q9_dict(state.get("question_snapshots"))
    snapshot = _q9_dict(snapshots.get("q9"))
    context_updates = _q9_dict(snapshot.get("context_updates"))
    diagnosis = _q9_dict(context_updates.get("q9_execution_diagnosis"))
    if _q9_text(diagnosis.get("authenticity_status")).lower() != "completed":
        return None
    result_payload = _q9_dict(context_updates.get("q9_action_posture") or snapshot.get("result"))
    if not result_payload:
        return None
    return CognitiveToolResult(
        tool_id=str(snapshot.get("tool_id") or NINE_QUESTION_Q9),
        summary=str(snapshot.get("summary") or "Preserved committed Q9 action posture"),
        proposals=[{"kind": "nine_question_q9_posture", "result": result_payload}],
        context_updates=context_updates,
        confidence=float(snapshot.get("confidence") or 0.8),
    )


class EvaluationProfile(BaseModel):
    """
    Q9 Result: Evaluation Standards.
    Derived from Q3/Q4/Q7.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    role_context: str = Field(..., description="Current role context.")
    resource_context: str = Field(..., description="Current resource status summary.")
    risk_level: str = Field(..., description="Overall risk level.")
    evaluation_weights: Dict[str, float] = Field(..., description="Weights for accuracy/speed/risk_control/creativity/continuity.")
    conservative_mode_triggered: bool = Field(default=False)
    evaluation_style: str = Field(..., description="logic/evidence threshold.")
    action_rhythm_hint: str = Field(
        default="steady_incremental",
        description="Suggested action rhythm such as steady_incremental or confirm_before_commit.",
    )


class EvolutionProfile(BaseModel):
    """
    Q9 Result: Evolution boundaries.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_directions: List[str] = Field(default_factory=list)
    risk_threshold: float = Field(default=0.1)
    forbidden_directions: List[str] = Field(default_factory=list)
    validation_requirements: List[str] = Field(default_factory=list)


class EscalationProfile(BaseModel):
    """
    Q9 Result: Escalation and Reconfirm rules.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    pause_conditions: List[str] = Field(default_factory=list)
    help_request_conditions: List[str] = Field(default_factory=list)
    confirmation_required_conditions: List[str] = Field(default_factory=list)
    revisit_conditions: List[str] = Field(default_factory=list)
    rollback_conditions: List[str] = Field(default_factory=list)


class ActionPlan(BaseModel):
    """
    Q9 Result: concrete ActionPlan for crossing from thinking into execution.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_action_plan: List[StrictStr] = Field(
        ...,
        min_length=1,
        description="Concrete executable steps required to reach the Q8 objective.",
    )
    method_selection: StrictStr = Field(
        ...,
        min_length=1,
        description="Why this method or toolchain is selected.",
    )
    required_resources: List[StrictStr] = Field(
        ...,
        min_length=1,
        description="Verified plugins, agents, internal budgets, or resources required by the plan.",
    )
    assigned_role_profile: StrictStr = Field(
        ...,
        min_length=1,
        description="Role subset or identity anchor assigned to the plan.",
    )
    risk_assessment: StrictStr = Field(
        ...,
        min_length=1,
        description="Side effects, SafetyGate, CloudAudit, or authorization risks.",
    )
    on_failure_action: StrictStr = Field(
        ...,
        min_length=1,
        description="Automatic compensation or rollback action when the plan fails or is blocked.",
    )
    estimated_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cognitive confidence for completing the plan.",
    )
    expected_results: List[StrictStr] = Field(
        ...,
        min_length=1,
        description="Exact expected physical or cognitive acceptance results if the plan succeeds.",
    )
    candidate_alternatives: List[StrictStr] = Field(
        ...,
        min_length=1,
        description="Fallback actions if the main plan fails or is blocked.",
    )
    nine_question_mapping: List[StrictStr] = Field(
        ...,
        min_length=1,
        description="Traceable Q1-Q8 evidence references used by the plan.",
    )


def _derive_compatibility_profiles(
    *,
    action_plan: dict[str, Any],
    posture_baseline: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Project ActionPlan into legacy posture fields still consumed by Q8/task overlays."""
    baseline_eval = _q9_dict(posture_baseline.get("evaluation_profile"))
    baseline_evol = _q9_dict(posture_baseline.get("evolution_profile"))
    baseline_esc = _q9_dict(posture_baseline.get("escalation_profile"))

    eval_profile = {
        "role_context": "q9_action_plan",
        "resource_context": "; ".join(_q9_list(action_plan.get("required_resources"))),
        "risk_level": _q9_text(baseline_eval.get("risk_level") or "medium"),
        "evaluation_weights": baseline_eval.get("evaluation_weights") or {
            "accuracy": 0.25,
            "risk_control": 0.35,
            "continuity": 0.25,
            "speed": 0.15,
        },
        "conservative_mode_triggered": bool(baseline_eval.get("conservative_mode_triggered")),
        "evaluation_style": _q9_text(baseline_eval.get("evaluation_style") or "action_plan_evidence_first"),
        "action_rhythm_hint": _q9_text(baseline_eval.get("action_rhythm_hint") or "steady_incremental"),
    }
    evol_profile = {
        "allowed_directions": list(action_plan.get("current_action_plan") or []),
        "risk_threshold": baseline_evol.get("risk_threshold", 0.1),
        "forbidden_directions": list(baseline_evol.get("forbidden_directions") or []),
        "validation_requirements": [
            "execute only through q4 verified_capabilities",
            *list(baseline_evol.get("validation_requirements") or []),
        ],
    }
    esc_profile = {
        "pause_conditions": list(baseline_esc.get("pause_conditions") or []),
        "help_request_conditions": list(baseline_esc.get("help_request_conditions") or []),
        "confirmation_required_conditions": list(baseline_esc.get("confirmation_required_conditions") or []),
        "revisit_conditions": list(action_plan.get("candidate_alternatives") or []),
        "rollback_conditions": list(baseline_esc.get("rollback_conditions") or []),
    }
    return eval_profile, evol_profile, esc_profile


# Pre-rebuild sub-profiles to resolve type hints for Pydantic v2
EvaluationProfile.model_rebuild()
EvolutionProfile.model_rebuild()
EscalationProfile.model_rebuild()
ActionPlan.model_rebuild()



class HowShouldIActPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    """
    [LLM MANDATORY] Q9 Phase Plugin.
    Determines the Action Posture based on the final decision (Q8) and environmental factors (Q1).
    """
    plugin_id: str = NINE_QUESTION_Q9
    display_name: str = "Q9: How should I act? (ActionPlan)"
    behavior_key: str = "q9_action_posture"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    rollback_conditions: List[str] = Field(default_factory=lambda: ["unhandled_llm_failure"])
    revocation_reasons: List[str] = Field(default_factory=list)
    tool_type: str = "nine_question"
    purpose: str = "Produce a concrete ten-field ActionPlan with resources, role anchors, risks, failure handling, confidence, expected results, alternatives, and Q1-Q8 references (Q9)."
    input_schema: Dict[str, Any] = {"type": "object"}
    output_schema: Dict[str, Any] = {"type": "object"}
    required_context: List[str] = ["plugin_service", "transcript_store", "llm_service"]
    trigger_conditions: List[str] = ["inspection", "always"]
    do_not_use_when: List[str] = ["missing_llm_service"]
    read_only: bool = True
    side_effect_free: bool = True
    is_default_version: bool = True
    is_official_release: bool = True

    def execute(self, context: Dict[str, Any], trace_id: str = "") -> Dict[str, Any]:
        """
        Synthesize action posture via LLM.
        """
        if trace_id and not context.get("trace_id"):
            context["trace_id"] = trace_id
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q9_module_runs = bind_module_runs(context, "q9")
        
        plugin_service = context.get("plugin_service")
        trace_id = str(context.get("trace_id") or f"q9-posture:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")

        functional_postures: list[dict[str, Any]] = []
        posture_oracles: list[str] = []
        functional_posture_run = start_module_run(
            q9_module_runs,
            "q9_functional_posture_chain",
            source="plugins.nine_questions.q9",
        )
        if plugin_service is None:
            fail_module_run(
                functional_posture_run,
                status="failed",
                error_code="plugin_service_missing",
                error_message="Functional posture chain not started.",
            )
            raise RuntimeError("Q9 requires plugin_service for functional posture execution.")
        try:
            functional_postures = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={"decision_trace": dict(context)},
                trace_id=trace_id,
                originator_id=session_id,
                caller_plugin_id=self.plugin_id,
            )
        except Exception as exc:
            logger.exception("Q9 functional posture chain failed")
            fail_module_run(
                functional_posture_run,
                error_code="q9_functional_posture_chain_failed",
                error_message=str(exc),
            )
            raise RuntimeError(f"Q9 functional posture chain failed: {exc}") from exc
        failed_postures = [
            item for item in functional_postures if not isinstance(item, dict) or item.get("status") != "done"
        ]
        if failed_postures:
            fail_module_run(
                functional_posture_run,
                status="failed",
                error_code="functional_posture_failed",
                error_message=f"Q9 functional posture plugins failed: {failed_postures}",
            )
            raise RuntimeError(f"Q9 functional posture plugins failed: {failed_postures}")
        posture_oracles = [
            str(item.get("plugin_id") or "")
            for item in functional_postures
            if item.get("status") == "done"
        ]
        if not posture_oracles:
            fail_module_run(
                functional_posture_run,
                status="failed",
                error_code="functional_posture_missing",
                error_message="Q9 requires at least one successful posture plugin result.",
            )
            raise RuntimeError("Q9 requires at least one successful posture plugin result.")
        finish_module_run(functional_posture_run)
        normalized_functional_postures = normalize_functional_postures(
            [
                {"plugin_id": item.get("plugin_id"), "result": item.get("result")}
                for item in functional_postures
                if item.get("status") == "done"
            ]
        )
        plugin_runs = [
            {
                "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                "feature_code": str(item.get("feature_code") or self.feature_code),
                "expected": True,
                "attempted": True,
                "status": "completed" if item.get("status") == "done" else "failed",
                "error_code": "" if item.get("status") == "done" else "posture_plugin_failed",
                "error_message": "" if item.get("status") == "done" else str(item.get("error") or "posture plugin failed"),
                "duration_ms": 0,
                "input_summary": {},
                "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
            for item in functional_postures
        ]
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_functional_posture_chain",
            payload={"q9_functional_postures": normalized_functional_postures, "plugin_runs": plugin_runs},
            status="completed",
            output_kind="evidence",
        )

        state_db_path = context.get("nine_question_state_db_path")
        q8_llm_output = load_q8_llm_output_from_table(db_path=state_db_path)
        raw_question_snapshot = normalize_snapshot_dict(
            {
                "q1": load_q1_llm_output_from_table(db_path=state_db_path),
                "q2": load_q2_llm_output_from_table(db_path=state_db_path),
                "q3": load_q3_llm_output_from_table(db_path=state_db_path),
                "q4": load_q4_llm_output_from_table(db_path=state_db_path),
                "q5": load_q5_llm_output_from_table(db_path=state_db_path),
                "q6": load_q6_llm_output_from_table(db_path=state_db_path),
                "q7": load_q7_llm_output_from_table(db_path=state_db_path),
                "q8": q8_llm_output,
            }
        )
        question_snapshot = _build_q9_posture_digest(raw_question_snapshot)
        raw_self_model = context.get("living_self_model") or context.get("self_model")
        raw_reasoning_budget = context.get("reasoning_budget") or context.get("budget")
        self_model = normalize_self_model(raw_self_model)
        reasoning_budget = normalize_reasoning_budget(raw_reasoning_budget)
        q1_q8 = dict(question_snapshot)
        nine_questions = context.get("nine_questions")
        if isinstance(nine_questions, dict):
            q1_q8["summaries"] = nine_questions
        q1_q8_validation_run = start_module_run(
            q9_module_runs,
            "q9_q1_q8_validation",
            source="plugins.nine_questions.q9",
        )
        upstream_dependencies = [
            build_question_dependency(question_id, payload=raw_question_snapshot.get(question_id), required=True)
            for question_id in ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8")
        ]
        invalid_dependencies = [
            item for item in upstream_dependencies if item["required"] and item["status"] != "completed"
        ]
        if invalid_dependencies:
            fail_module_run(
                q1_q8_validation_run,
                status="failed",
                error_code="upstream_dependency_invalid",
                error_message=f"Q9 requires completed Q1-Q8 SQLite LLM outputs: {invalid_dependencies}",
            )
            raise RuntimeError(f"Q9 requires completed Q1-Q8 SQLite LLM outputs: {invalid_dependencies}")
        finish_module_run(q1_q8_validation_run)
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_q1_q8_validation",
            payload={
                "q9_q1_q8_snapshot": raw_question_snapshot,
                "q9_posture_digest": question_snapshot,
            },
            status="completed",
            output_kind="validation",
        )
        self_model_validation_run = start_module_run(
            q9_module_runs,
            "q9_self_model_source_validation",
            source="plugins.nine_questions.q9",
        )
        if not self_model:
            fail_module_run(
                self_model_validation_run,
                status="failed",
                error_code="self_model_missing",
                error_message="Q9 requires real self-model input.",
            )
            raise RuntimeError("Q9 requires real self-model input.")
        finish_module_run(self_model_validation_run)
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_self_model_source_validation",
            payload={"q9_self_model": self_model},
            status="completed",
            output_kind="validation",
        )
        reasoning_budget_validation_run = start_module_run(
            q9_module_runs,
            "q9_reasoning_budget_source_validation",
            source="plugins.nine_questions.q9",
        )
        if not reasoning_budget:
            fail_module_run(
                reasoning_budget_validation_run,
                status="failed",
                error_code="reasoning_budget_missing",
                error_message="Q9 requires real reasoning budget input.",
            )
            raise RuntimeError("Q9 requires real reasoning budget input.")
        finish_module_run(reasoning_budget_validation_run)
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_reasoning_budget_source_validation",
            payload={"q9_reasoning_budget": reasoning_budget},
            status="completed",
            output_kind="validation",
        )
        posture_baseline_run = start_module_run(
            q9_module_runs,
            "q9_posture_baseline_projection",
            source="plugins.nine_questions.q9",
        )
        posture_baseline = derive_posture_baseline(
            q1_q8,
            self_model,
            reasoning_budget,
            normalized_functional_postures,
        )
        finish_module_run(posture_baseline_run)
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_posture_baseline_projection",
            payload=posture_baseline,
            status="completed",
            output_kind="inference",
        )

        failure_caller_context = build_caller_context(
            invocation_phase="nine_question_q9_task_module_orchestration",
            source_module="q9_how_should_i_act_plugin",
            question_ref="我应该如何行动",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )
        posture_projection_run = start_module_run(
            q9_module_runs,
            "q9_posture_control_projection",
            source="plugins.nine_questions.q9",
        )

        try:
            internal_task_result = run_q9_internal_task_generation(
                context=context,
                provider=provider,
                transcript_store=transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                decision_id=decision_id,
                q9_module_runs=q9_module_runs,
                q1_q8=q1_q8,
                upstream_llm_outputs=raw_question_snapshot,
                posture_baseline=posture_baseline,
                self_model=self_model,
                reasoning_budget=reasoning_budget,
            )
            external_task_result = run_q9_external_task_generation(
                context=context,
                provider=provider,
                transcript_store=transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                decision_id=decision_id,
                q9_module_runs=q9_module_runs,
                q1_q8=q1_q8,
                upstream_llm_outputs=raw_question_snapshot,
                posture_baseline=posture_baseline,
            )
            finish_module_run(posture_projection_run)
            result_payload = {
                "q9_internal_llm_input": internal_task_result.get("llm_input") or {},
                "q9_internal_llm_output": internal_task_result.get("llm_output") or {},
                "q9_external_llm_input": external_task_result.get("llm_input") or {},
                "q9_external_llm_output": external_task_result.get("llm_output") or {},
            }
            posture_projection = {
                "q9_action_plan": {
                    "internal": internal_task_result.get("action_plan") or {},
                    "external": external_task_result.get("action_plan") or {},
                },
                "internal_plan": internal_task_result.get("plan") or {},
                "external_plan": external_task_result.get("plan") or {},
            }
            persist_question_module_output(
                context,
                question_id="q9",
                module_id="q9_posture_control_projection",
                payload=posture_projection,
                status="completed",
                output_kind="inference",
            )
            q9_execution_diagnosis = question_authenticity_judgment(
                module_runs=q9_module_runs,
                upstream_dependencies=upstream_dependencies,
                used_fallback=False,
                diagnosis_code="q9_completed",
                diagnosis_message="Q9 completed with authoritative Q1-Q8 SQLite LLM inputs and Q9 internal/external LLM IO persisted.",
                required_modules=[
                    "q9_functional_posture_chain",
                    "q9_q1_q8_validation",
                    "q9_self_model_source_validation",
                    "q9_reasoning_budget_source_validation",
                    "q9_posture_baseline_projection",
                    "q9_posture_control_projection",
                    "q9_internal_task_generation",
                    "q9_external_task_generation",
                ],
            )
            q9_execution_diagnosis["plugin_runs"] = plugin_runs
            context_updates = {
                **result_payload,
                "q9_execution_diagnosis": q9_execution_diagnosis,
                **posture_projection,
            }
            return CognitiveToolResult(
                tool_id=self.plugin_id,
                summary="Saved Q9 internal/external LLM input and output",
                proposals=[
                    {
                        "kind": "nine_question_q9_llm_io",
                        "result": result_payload,
                    }
                ],
                context_updates=context_updates,
                llm_output=result_payload,
                llm_trace_payload={},
                confidence=0.8,
            )

        except Exception as exc:
            fail_module_run(
                posture_projection_run,
                error_code="q9_execution_failed",
                error_message=str(exc),
            )
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q9_how_should_i_act",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我应该如何行动",
                    "caller_context": failure_caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            # 严禁把 Q9 LLM 故障伪装成“只是没有数据”或静默降级。
            # 这里必须保留完整异常日志与堆栈，避免后台已失效但页面仍表现为系统正常。
            logger.exception("Q9 LLM synthesis failed")
            raise RuntimeError(f"[LLM MANDATORY] Q9 synthesis failed: {exc}") from exc

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        try:
            result = self.execute(dict(context))
        except Exception as exc:
            logger.exception("Q9 run_tool failed")
            raise RuntimeError(f"[LLM MANDATORY] Q9 run_tool failed: {exc}") from exc
        if isinstance(result, CognitiveToolResult):
            return result
        payload = _q9_dict(result)
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Saved Q9 internal/external LLM input and output",
            proposals=[{"kind": "nine_question_q9_llm_io", "result": payload}],
            context_updates=payload,
            llm_output=payload,
            llm_trace_payload={},
            confidence=0.8,
        )


def build_q9_how_should_i_act_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q9,
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> HowShouldIActPlugin:
    return HowShouldIActPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q9",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )


HowShouldIActPlugin.model_rebuild()
