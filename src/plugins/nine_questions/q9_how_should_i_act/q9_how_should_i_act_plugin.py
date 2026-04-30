from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q9
from zentex.plugins.models import PluginLifecycleStatus
from plugins.nine_questions.q9_how_should_i_act.modules import (
    coerce_string_list,
    derive_posture_baseline,
    merge_string_lists,
    normalize_functional_postures,
    normalize_q8_profile,
    normalize_ratio,
    normalize_reasoning_budget,
    normalize_self_model,
    normalize_snapshot_dict,
    normalize_text,
)
from zentex.common.nine_questions_shared import (
    build_nine_question_partial_failure,
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
    run_audit_integration,
    run_learning_integration,
    load_authoritative_question_bundle_from_storage,
    run_memory_integration,
    run_reflection_integration,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_nine_questions_snapshot,
    render_plugin_catalog,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.plugins.service import (
    execute_enabled_cognitive_plugin_functionals,
)
from plugins.nine_questions.q9_how_should_i_act.llm_prompt import build_q9_llm_request

logger = logging.getLogger(__name__)


def _q9_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _q9_text(value: Any, *, max_chars: int = 500) -> str:
    return str(value or "").strip()[:max_chars]


def _q9_list(value: Any, *, limit: int = 6, max_chars: int = 180) -> list[Any]:
    if not isinstance(value, list):
        return []
    result: list[Any] = []
    for item in value:
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            compact = {
                str(key): _q9_text(val, max_chars=max_chars)
                for key, val in item.items()
                if val not in (None, "", [], {})
            }
            if compact:
                result.append(compact)
        else:
            result.append(_q9_text(item, max_chars=max_chars))
        if len(result) >= limit:
            break
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
    q2_role = _q9_dict(q2.get("q2_role_profile") or q2.get("identity_kernel_snapshot"))
    q3_resource = _q9_dict(q3.get("q3_resource_evaluation"))
    q4_profile = _q9_dict(q4.get("q4_capability_boundary_profile") or q4.get("q4_capability_baseline"))
    q5_profile = _q9_dict(q5.get("q5_authorization_boundary_profile") or q5.get("q5_authorization_baseline"))
    q6_profile = _q9_dict(q6.get("q6_forbidden_zone_profile") or q6.get("q6_forbidden_zone_baseline"))
    q7_profile = _q9_dict(q7.get("q7_alternative_strategy_profile") or q7.get("q7_alternative_strategy_baseline"))
    q8_result = _q9_dict(q8.get("q8_objective_and_queue") or q8)
    q8_objective = _q9_dict(q8_result.get("objective") or q8.get("q8_objective_profile"))
    q8_queue = _q9_dict(q8_result.get("task_queue") or q8.get("q8_task_queue"))

    return {
        "q1": {
            "status": _q9_status(q1, "q1_execution_diagnosis"),
            "environment_summary": _q9_text(q1.get("summary")),
            "primary_domain": _q9_text(q1_scene.get("primary_domain")),
            "uncertainty": _q9_dict(q1.get("q1_uncertainty_profile")),
        },
        "q2": {
            "status": _q9_status(q2, "q2_execution_diagnosis"),
            "identity_role": _q9_text(q2_role.get("identity_role")),
            "active_role": _q9_text(q2_role.get("active_role")),
            "task_role": _q9_text(q2_role.get("task_role")),
            "constraints": _q9_list(q2.get("non_bypassable_constraints"), limit=4),
        },
        "q3": {
            "status": _q9_status(q3, "q3_execution_diagnosis"),
            "resource_status": _q9_text(q3_resource.get("resource_status")),
            "bottleneck_node": _q9_text(q3_resource.get("bottleneck_node")),
            "missing_critical_assets": _q9_list(q3_resource.get("missing_critical_assets"), limit=6),
        },
        "q4": {
            "status": _q9_status(q4, "q4_execution_diagnosis"),
            "actionable_space": _q9_list(q4_profile.get("actionable_space"), limit=8),
            "capability_upper_limits": _q9_list(q4_profile.get("capability_upper_limits"), limit=8),
        },
        "q5": {
            "status": _q9_status(q5, "q5_execution_diagnosis"),
            "allowed_action_space": _q9_list(q5_profile.get("allowed_action_space"), limit=8),
            "forbidden_action_space": _q9_list(q5_profile.get("forbidden_action_space"), limit=8),
            "requires_escalation_actions": _q9_list(q5_profile.get("requires_escalation_actions"), limit=6),
        },
        "q6": {
            "status": _q9_status(q6, "q6_execution_diagnosis"),
            "absolute_red_lines": _q9_list(q6_profile.get("absolute_red_lines"), limit=10),
            "performance_tradeoff_bans": _q9_list(q6_profile.get("performance_tradeoff_bans"), limit=8),
            "prohibited_strategies": _q9_list(q6_profile.get("prohibited_strategies"), limit=8),
        },
        "q7": {
            "status": _q9_status(q7, "q7_execution_diagnosis"),
            "fallback_plans": _q9_list(q7_profile.get("fallback_plans"), limit=8),
            "degradation_strategies": _q9_list(q7_profile.get("degradation_strategies"), limit=8),
            "collaboration_switches": _q9_list(q7_profile.get("collaboration_switches"), limit=6),
        },
        "q8": {
            "status": _q9_status(q8, "q8_execution_diagnosis"),
            "current_mission": _q9_text(q8_objective.get("current_mission") or q8.get("summary")),
            "current_phase_tasks": _q9_list(q8_objective.get("current_phase_tasks"), limit=8),
            "priority_order": _q9_list(q8_objective.get("priority_order"), limit=8),
            "next_self_tasks": _q9_list(q8_queue.get("next_self_tasks"), limit=8),
            "blocked_self_tasks": _q9_list(q8_queue.get("blocked_self_tasks"), limit=6),
            "proactive_actions": _q9_list(q8_queue.get("proactive_actions"), limit=6),
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


def _record_q9_downstream_failure_nodes(
    context: Dict[str, Any],
    *,
    module_runs: list[dict[str, Any]],
    error_code: str,
    error_message: str,
) -> None:
    failure_payload = {
        "q9_q1_q8_snapshot": normalize_snapshot_dict(
            load_authoritative_question_bundle_from_storage(
                context, ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"]
            )
        ),
        "q9_self_model": normalize_self_model(
            context.get("living_self_model") or context.get("self_model")
        ),
        "q9_reasoning_budget": normalize_reasoning_budget(
            context.get("reasoning_budget") or context.get("budget")
        ),
    }
    module_specs = [
        ("q9_audit_integration", "audit", "Q9 posture unavailable; audit integration skipped."),
        ("q9_memory_integration", "memory", "Q9 posture unavailable; memory integration skipped."),
        ("q9_reflection_integration", "reflection", "Q9 posture unavailable; reflection integration skipped."),
        ("q9_learning_integration", "learning", "Q9 posture unavailable; learning integration skipped."),
    ]
    for module_id, module_kind, summary in module_specs:
        run = start_module_run(module_runs, module_id, source="plugins.nine_questions.q9")
        finish_module_run(
            run,
            status="missing",
            error_code=error_code,
            error_message=error_message,
        )
        run["data"] = {
            "question_id": "q9",
            "module_kind": module_kind,
            "summary": summary,
            "payload": json_safe_payload(failure_payload),
            "trace_id": str(context.get("trace_id") or "q9:downstream_failure"),
        }
        persist_question_module_output(
            context,
            question_id="q9",
            module_id=module_id,
            payload=run["data"],
            status="missing",
            output_kind="integration",
            extra={
                "error_code": error_code,
                "error_message": error_message,
            },
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

# Pre-rebuild sub-profiles to resolve type hints for Pydantic v2
EvaluationProfile.model_rebuild()
EvolutionProfile.model_rebuild()
EscalationProfile.model_rebuild()



class HowShouldIActPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    """
    [LLM MANDATORY] Q9 Phase Plugin.
    Determines the Action Posture based on the final decision (Q8) and environmental factors (Q1).
    """
    plugin_id: str = NINE_QUESTION_Q9
    display_name: str = "Q9: How should I act? (Posture & Rhythm)"
    behavior_key: str = "q9_action_posture"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    rollback_conditions: List[str] = Field(default_factory=lambda: ["unhandled_llm_failure"])
    revocation_reasons: List[str] = Field(default_factory=list)
    tool_type: str = "nine_question"
    purpose: str = "Determine action posture, evaluation style, and confirmation strategy (Q9)."
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
        if plugin_service is not None:
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
                # 严禁吞掉 Q9 posture plugin 链异常并继续伪装“只是没有姿态建议”。
                # 这里必须结构化失败并保留异常日志，否则后台故障会被误判为正常降级。
                logger.exception("Q9 functional posture chain failed")
                fail_module_run(
                    functional_posture_run,
                    error_code="q9_functional_posture_chain_failed",
                    error_message=str(exc),
                )
                raise RuntimeError(f"Q9 functional posture chain failed: {exc}") from exc
            posture_oracles = [
                str(item.get("plugin_id") or "")
                for item in functional_postures
                if item.get("status") == "done"
            ]
            finish_module_run(
                functional_posture_run,
                status="completed" if functional_postures else "ready",
                error_code="" if functional_postures else "functional_posture_missing",
                error_message="" if functional_postures else "No posture plugins executed.",
            )
        else:
            finish_module_run(
                functional_posture_run,
                status="missing",
                error_code="plugin_service_missing",
                error_message="Functional posture chain not started.",
            )
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

        question_snapshot = normalize_snapshot_dict(
            load_authoritative_question_bundle_from_storage(context, ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"])
        )
        question_snapshot = _build_q9_posture_digest(question_snapshot)
        self_model = normalize_self_model(
            context.get("living_self_model") or context.get("self_model")
        )
        reasoning_budget = normalize_reasoning_budget(
            context.get("reasoning_budget") or context.get("budget")
        )
        # 从 authoritative question_snapshots 读取 Q1-Q8 积累的认知摘要
        nine_questions = context.get("nine_questions") or {}
        # 构建 Q1-Q8 的 profiles 摘要（用于 LLM 输入）
        q1_q8 = question_snapshot or {
            "q1": {},
            "q2": {},
            "q3": {},
            "q4": {},
            "q5": {},
            "q6": {},
            "q7": {},
            "q8": {},
            "summaries": nine_questions,
        }
        if "summaries" not in q1_q8:
            q1_q8["summaries"] = nine_questions
        q1_q8_validation_run = start_module_run(
            q9_module_runs,
            "q9_q1_q8_validation",
            source="plugins.nine_questions.q9",
        )
        has_q8_basis = bool(q1_q8.get("q8"))
        finish_module_run(
            q1_q8_validation_run,
            status="completed" if has_q8_basis else "missing",
            error_code="" if has_q8_basis else "q8_basis_missing",
            error_message="" if has_q8_basis else "Q8 objective basis is missing.",
        )
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_q1_q8_validation",
            payload={"q9_q1_q8_snapshot": q1_q8},
            status=str(q1_q8_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )
        self_model_validation_run = start_module_run(
            q9_module_runs,
            "q9_self_model_source_validation",
            source="plugins.nine_questions.q9",
        )
        has_self_model = bool(self_model)
        finish_module_run(
            self_model_validation_run,
            status="completed" if has_self_model else "ready",
            error_code="" if has_self_model else "self_model_missing",
            error_message="" if has_self_model else "Self-model is missing or snapshot-only.",
        )
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_self_model_source_validation",
            payload={"q9_self_model": self_model},
            status=str(self_model_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )
        reasoning_budget_validation_run = start_module_run(
            q9_module_runs,
            "q9_reasoning_budget_source_validation",
            source="plugins.nine_questions.q9",
        )
        has_reasoning_budget = bool(reasoning_budget)
        finish_module_run(
            reasoning_budget_validation_run,
            status="completed" if has_reasoning_budget else "ready",
            error_code="" if has_reasoning_budget else "reasoning_budget_missing",
            error_message="" if has_reasoning_budget else "Reasoning budget is missing or default-only.",
        )
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_reasoning_budget_source_validation",
            payload={"q9_reasoning_budget": reasoning_budget},
            status=str(reasoning_budget_validation_run.get("status") or "completed"),
            output_kind="evidence",
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
            status=str(posture_baseline_run.get("status") or "completed"),
            output_kind="evidence",
        )

        # 2. Build synthesis prompt
        system_prompt = (
            "你现在是 G19 Preference AI 的行动姿态与风格控制中枢。请严格基于当前的主目标（Q8）等认知概览。\n"
            "你的任务不是生成具体的执行动作，而是为接下来的行动定下『基调』。"
        )
        posture_catalog = render_plugin_catalog(posture_oracles, heading="可用姿态策略插件")
        q1_q8_summary = render_nine_questions_snapshot(q1_q8)

        llm_request = build_q9_llm_request(
            system_prompt=system_prompt,
            q1_q8_summary=q1_q8_summary,
            posture_catalog=posture_catalog,
            posture_baseline=posture_baseline,
            q1_q8=q1_q8,
            self_model=self_model,
            reasoning_budget=reasoning_budget,
            posture_oracles=posture_oracles,
            functional_postures=normalized_functional_postures,
        )
        user_prompt = llm_request["prompt"]
        model_context = dict(llm_request["model_context"])
        requested_timeout = context.get("request_timeout_seconds")
        fallback_timeout = context.get("llm_request_timeout_seconds")
        try:
            timeout_seconds = float(requested_timeout or fallback_timeout or 240.0)
        except (TypeError, ValueError):
            timeout_seconds = 240.0
        model_context["request_timeout_seconds"] = max(5.0, min(timeout_seconds, 240.0))

        # 3. Invoke LLM with strict traceability
        caller_context = build_caller_context(
            invocation_phase="nine_question_q9_posture",
            source_module="q9_how_should_i_act_plugin",
            question_ref="我应该如何行动",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q9_how_should_i_act",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": "我应该如何行动",
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )
        posture_projection_run = start_module_run(
            q9_module_runs,
            "q9_posture_control_projection",
            source="plugins.nine_questions.q9",
        )

        try:
            started = perf_counter()
            result_raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context=model_context,
                caller_context=caller_context
            )
            elapsed_ms = int((perf_counter() - started) * 1000)

            eval_prof = EvaluationProfile.model_validate(
                {
                    **(result_raw.get("evaluation_profile", {}) if isinstance(result_raw.get("evaluation_profile"), dict) else {}),
                    "role_context": normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("role_context")
                    ) or posture_baseline["evaluation_profile"]["role_context"],
                    "resource_context": normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("resource_context")
                    ) or posture_baseline["evaluation_profile"]["resource_context"],
                    "risk_level": normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("risk_level")
                    ) or posture_baseline["evaluation_profile"]["risk_level"],
                    "evaluation_style": normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("evaluation_style")
                    ) or posture_baseline["evaluation_profile"]["evaluation_style"],
                    "action_rhythm_hint": normalize_text(
                        (result_raw.get("evaluation_profile", {}) or {}).get("action_rhythm_hint")
                    ) or posture_baseline["evaluation_profile"].get("action_rhythm_hint") or "steady_incremental",
                    "conservative_mode_triggered": bool(
                        (result_raw.get("evaluation_profile", {}) or {}).get("conservative_mode_triggered")
                        or posture_baseline["evaluation_profile"]["conservative_mode_triggered"]
                    ),
                    "evaluation_weights": (
                        (result_raw.get("evaluation_profile", {}) or {}).get("evaluation_weights")
                        if isinstance((result_raw.get("evaluation_profile", {}) or {}).get("evaluation_weights"), dict)
                        else {
                            "accuracy": 0.35,
                            "speed": 0.1 if posture_baseline["evaluation_profile"]["conservative_mode_triggered"] else 0.2,
                            "risk_control": 0.3,
                            "creativity": 0.1,
                            "continuity": 0.15,
                        }
                    ),
                }
            )
            evol_prof = EvolutionProfile.model_validate(
                {
                    **(result_raw.get("evolution_profile", {}) if isinstance(result_raw.get("evolution_profile"), dict) else {}),
                    "allowed_directions": merge_string_lists(
                        coerce_string_list((result_raw.get("evolution_profile", {}) or {}).get("allowed_directions")),
                        posture_baseline["evolution_profile"]["allowed_directions"],
                    ),
                    "forbidden_directions": merge_string_lists(
                        coerce_string_list((result_raw.get("evolution_profile", {}) or {}).get("forbidden_directions")),
                        posture_baseline["evolution_profile"]["forbidden_directions"],
                    ),
                    "validation_requirements": merge_string_lists(
                        coerce_string_list((result_raw.get("evolution_profile", {}) or {}).get("validation_requirements")),
                        posture_baseline["evolution_profile"]["validation_requirements"],
                    ),
                    "risk_threshold": (
                        float((result_raw.get("evolution_profile", {}) or {}).get("risk_threshold"))
                        if isinstance((result_raw.get("evolution_profile", {}) or {}).get("risk_threshold"), (int, float))
                        else posture_baseline["evolution_profile"]["risk_threshold"]
                    ),
                }
            )
            esc_prof = EscalationProfile.model_validate(
                {
                    **(result_raw.get("escalation_profile", {}) if isinstance(result_raw.get("escalation_profile"), dict) else {}),
                    "pause_conditions": merge_string_lists(
                        coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("pause_conditions")),
                        posture_baseline["escalation_profile"]["pause_conditions"],
                    ),
                    "help_request_conditions": merge_string_lists(
                        coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("help_request_conditions")),
                        posture_baseline["escalation_profile"]["help_request_conditions"],
                    ),
                    "confirmation_required_conditions": merge_string_lists(
                        coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("confirmation_required_conditions")),
                        posture_baseline["escalation_profile"]["confirmation_required_conditions"],
                    ),
                    "revisit_conditions": coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("revisit_conditions")),
                    "rollback_conditions": merge_string_lists(
                        coerce_string_list((result_raw.get("escalation_profile", {}) or {}).get("rollback_conditions")),
                        posture_baseline["escalation_profile"]["rollback_conditions"],
                    ),
                }
            )

            record_model_completed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q9_how_should_i_act",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我应该如何行动",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": result_raw,
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                    "elapsed_ms": elapsed_ms,
                },
            )

            authenticity_status = (
                "completed"
                if has_q8_basis and plugin_service is not None
                else "degraded"
            )
            finish_module_run(
                posture_projection_run,
                status="completed" if authenticity_status == "completed" else "degraded",
                error_code="" if authenticity_status == "completed" else "posture_projection_degraded",
                error_message="" if authenticity_status == "completed" else "Posture recommendation was generated without full basis verification.",
            )
            q9_execution_diagnosis = {
                "authenticity_status": authenticity_status,
                "diagnosis_code": "posture_control_degraded" if authenticity_status != "completed" else "completed",
                "diagnosis_message": (
                    "Q9 posture output relies on incomplete Q8/self-model/budget/plugin evidence."
                    if authenticity_status != "completed"
                    else "Q9 posture output completed with validated Q8, self-model, budget, and plugin evidence."
                ),
                "used_fallback": authenticity_status != "completed",
                "upstream_degraded": not has_q8_basis,
                "module_runs": list(q9_module_runs),
                "plugin_runs": plugin_runs,
                "upstream_dependencies": [
                    {
                        "dependency_id": "q8",
                        "required": True,
                        "status": "completed" if has_q8_basis else "missing",
                        "message": "Q8 objective profile is required for Q9 posture control.",
                    }
                ],
                "recovery_plan": build_recovery_plan(
                    question_id="q9",
                    retriable=True,
                    rollback_available=False,
                    partial_retry_available=True,
                    partial_replace_available=False,
                    actions=[
                        build_recovery_action(
                            "q9-rerun-question",
                            label="重跑 Q9",
                            kind="retry",
                            executable=True,
                            scope="question",
                            target="q9",
                            reason="重新执行行动姿态推导。",
                            path="/api/web/nine-questions/q9/run",
                        ),
                        build_recovery_action(
                            "q9-rerun-upstream-q8",
                            label="先重跑 Q8 再重跑 Q9",
                            kind="partial_retry",
                            executable=True,
                            scope="upstream_chain",
                            target="q8->q9",
                            reason="Q9 依赖 Q8 主目标和任务队列。",
                            path="/api/web/nine-questions/q8/run",
                        ),
                        build_recovery_action(
                            "q9-refresh-posture-inputs",
                            label="刷新 Q9 姿态输入模块",
                            kind="partial_retry",
                            executable=True,
                            scope="module",
                            target="q9_functional_posture_chain",
                            reason="仅刷新 Q9 self-model/budget/posture plugin baseline；不伪装重跑 LLM 姿态投影。",
                            path="/api/web/nine-questions/q9/modules/q9_functional_posture_chain/retry",
                        ),
                    ],
                ),
            }
            persist_question_module_output(
                context,
                question_id="q9",
                module_id="q9_posture_control_projection",
                payload={
                    "evaluation_profile": eval_prof.model_dump(mode="json"),
                    "evolution_profile": evol_prof.model_dump(mode="json"),
                    "escalation_profile": esc_prof.model_dump(mode="json"),
                },
                status=str(posture_projection_run.get("status") or "completed"),
                output_kind="inference",
            )

            result_payload = {
                "evaluation_profile": eval_prof.model_dump(mode="json"),
                "evolution_profile": evol_prof.model_dump(mode="json"),
                "escalation_profile": esc_prof.model_dump(mode="json"),
                "q1_q8_snapshot": q1_q8,
                "q9_self_model": self_model,
                "q9_reasoning_budget": reasoning_budget,
                "q9_posture_baseline": posture_baseline,
                "q9_functional_postures": normalized_functional_postures,
                "q9_execution_diagnosis": q9_execution_diagnosis,
            }
            eval_payload = result_payload["evaluation_profile"]
            evol_payload = result_payload["evolution_profile"]
            esc_payload = result_payload["escalation_profile"]
            q9_module_runs = q9_execution_diagnosis.get("module_runs")
            q9_module_runs = q9_module_runs if isinstance(q9_module_runs, list) else []
            run_audit_integration(
                context,
                question_id="q9",
                module_runs=q9_module_runs,
                summary="Q9 姿态与升级策略审计已记录。",
                payload={
                    "q9_evaluation_profile": eval_payload,
                    "q9_evolution_profile": evol_payload,
                    "q9_escalation_profile": esc_payload,
                    "q9_posture_baseline": result_payload.get("q9_posture_baseline") or {},
                },
            )
            run_memory_integration(
                context,
                question_id="q9",
                module_runs=q9_module_runs,
                title=f"Q9 Action Posture {trace_id}",
                summary="Q9 行动姿态已写入记忆。",
                layer="episodic",
                payload={
                    "q9_trace_id": trace_id,
                    "q9_evaluation_profile": eval_payload,
                    "q9_evolution_profile": evol_payload,
                    "q9_escalation_profile": esc_payload,
                },
                tags=["nine-questions", "q9", "action-posture"],
            )
            run_reflection_integration(
                context,
                question_id="q9",
                module_runs=q9_module_runs,
                subject="Q9 action posture",
                summary="Q9 posture 平衡性反思已记录。",
                reflection_type="action_reflection",
                payload={
                    "q9_evaluation_profile": eval_payload,
                    "q9_posture_baseline": result_payload.get("q9_posture_baseline") or {},
                },
            )
            run_learning_integration(
                context,
                question_id="q9",
                module_runs=q9_module_runs,
                learning_kind="action_posture",
                summary="Q9 action posture 学习记录已登记。",
                payload={
                    "q9_evaluation_profile": eval_payload,
                    "q9_escalation_profile": esc_payload,
                },
            )
            q9_execution_diagnosis["module_runs"] = q9_module_runs
            result_payload["q9_execution_diagnosis"] = q9_execution_diagnosis
            summary_q9 = (
                f"style={eval_payload.get('evaluation_style','')}; "
                f"risk={eval_payload.get('risk_level','')}; "
                f"conservative={eval_payload.get('conservative_mode_triggered','')}"
            )
            return CognitiveToolResult(
                tool_id=self.plugin_id,
                summary="Synthesized action posture profile (Q9)",
                proposals=[
                    {
                        "kind": "nine_question_q9_posture",
                        "result": result_payload,
                    }
                ],
                context_updates={
                    "nine_questions": {"我应该如何行动": summary_q9},
                    "q9_action_posture": result_payload,
                    "q9_evaluation_profile": eval_payload,
                    "q9_evolution_profile": evol_payload,
                    "q9_escalation_profile": esc_payload,
                    "q9_q1_q8_snapshot": result_payload.get("q1_q8_snapshot") or {},
                    "q9_self_model": result_payload.get("q9_self_model") or {},
                    "q9_reasoning_budget": result_payload.get("q9_reasoning_budget") or {},
                    "q9_posture_baseline": result_payload.get("q9_posture_baseline") or {},
                    "q9_functional_postures": result_payload.get("q9_functional_postures") or [],
                    "q9_execution_diagnosis": q9_execution_diagnosis,
                },
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
                    "caller_context": caller_context.model_dump(mode="json"),
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
            # 严禁在 run_tool 兜底层吞掉异常并只返回 partial_failed 而不打日志。
            # 否则 execute 链路提前失败时，监控面会只看到失败结果，却看不到后台真实异常。
            logger.exception("Q9 run_tool failed")
            failed_module_runs = bind_module_runs(context, "q9")
            posture_projection_run = start_module_run(
                failed_module_runs,
                "q9_posture_control_projection",
                source="plugins.nine_questions.q9",
            )
            fail_module_run(
                posture_projection_run,
                error_code="q9_execution_failed",
                error_message=str(exc),
            )
            question_snapshot = normalize_snapshot_dict(
                load_authoritative_question_bundle_from_storage(context, ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"])
            )
            question_snapshot["q8"] = normalize_q8_profile(question_snapshot.get("q8"))
            self_model = normalize_self_model(
                context.get("living_self_model") or context.get("self_model")
            )
            reasoning_budget = normalize_reasoning_budget(
                context.get("reasoning_budget") or context.get("budget")
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q9",
                question_ref="我应该如何行动",
                error_code="q9_execution_failed",
                error_message=str(exc),
                diagnosis_key="q9_execution_diagnosis",
                module_runs=list(failed_module_runs),
                plugin_runs=[],
                upstream_dependencies=[],
                context_updates={
                    "q9_q1_q8_snapshot": question_snapshot,
                    "q9_self_model": self_model,
                    "q9_reasoning_budget": reasoning_budget,
                },
                required_modules=["q9_posture_control_projection"],
            )
        eval_prof = result.get("evaluation_profile") or {}
        evol_prof = result.get("evolution_profile") or {}
        esc_prof = result.get("escalation_profile") or {}
        summary_q9 = (
            f"style={eval_prof.get('evaluation_style','')}; "
            f"risk={eval_prof.get('risk_level','')}; "
            f"conservative={eval_prof.get('conservative_mode_triggered','')}"
        )
        q9_execution_diagnosis = result.get("q9_execution_diagnosis") or {}
        q9_module_runs = q9_execution_diagnosis.get("module_runs")
        q9_module_runs = q9_module_runs if isinstance(q9_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q9",
            module_runs=q9_module_runs,
            summary="Q9 姿态与升级策略审计已记录。",
            payload={
                "q9_evaluation_profile": eval_prof,
                "q9_evolution_profile": evol_prof,
                "q9_escalation_profile": esc_prof,
                "q9_posture_baseline": result.get("q9_posture_baseline") or {},
            },
        )
        run_memory_integration(
            context,
            question_id="q9",
            module_runs=q9_module_runs,
            title=f"Q9 Action Posture {trace_id}",
            summary="Q9 行动姿态已写入记忆。",
            layer="episodic",
            payload={
                "q9_trace_id": trace_id,
                "q9_evaluation_profile": eval_prof,
                "q9_evolution_profile": evol_prof,
                "q9_escalation_profile": esc_prof,
            },
            tags=["nine-questions", "q9", "action-posture"],
        )
        run_reflection_integration(
            context,
            question_id="q9",
            module_runs=q9_module_runs,
            subject="Q9 action posture",
            summary="Q9 posture 平衡性反思已记录。",
            reflection_type="action_reflection",
            payload={
                "q9_evaluation_profile": eval_prof,
                "q9_posture_baseline": result.get("q9_posture_baseline") or {},
            },
        )
        run_learning_integration(
            context,
            question_id="q9",
            module_runs=q9_module_runs,
            learning_kind="action_posture",
            summary="Q9 action posture 学习记录已登记。",
            payload={
                "q9_evaluation_profile": eval_prof,
                "q9_escalation_profile": esc_prof,
            },
        )
        q9_execution_diagnosis["module_runs"] = q9_module_runs
        result["q9_execution_diagnosis"] = q9_execution_diagnosis

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Synthesized action posture profile (Q9)",
            proposals=[
                {
                    "kind": "nine_question_q9_posture",
                    "result": result,
                }
            ],
            context_updates={
                "nine_questions": {"我应该如何行动": summary_q9},
                "q9_evaluation_profile": eval_prof,
                "q9_evolution_profile": evol_prof,
                "q9_escalation_profile": esc_prof,
                "q9_q1_q8_snapshot": result.get("q1_q8_snapshot") or {},
                "q9_self_model": result.get("q9_self_model") or {},
                "q9_reasoning_budget": result.get("q9_reasoning_budget") or {},
                "q9_posture_baseline": result.get("q9_posture_baseline") or {},
                "q9_functional_postures": result.get("q9_functional_postures") or [],
                "q9_execution_diagnosis": q9_execution_diagnosis,
            },
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
