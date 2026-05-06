from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q3_role_inference.llm_output_table import (
    load_llm_output_from_table as load_q3_llm_output_from_table,
)
from plugins.nine_questions.q4_what_can_i_do.llm_output_table import (
    load_llm_output_from_table as load_q4_llm_output_from_table,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_output_table import (
    load_llm_output_from_table as load_q5_llm_output_from_table,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q6
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q6_what_should_i_not_do.internal import (
    derive_forbidden_zone_baseline,
    normalize_redline_inputs,
)
from plugins.nine_questions.q6_what_should_i_not_do.external import (
    collect_external_redline_inputs,
)
from plugins.nine_questions.q6_what_should_i_not_do.models import (
    ForbiddenZoneProfile,
    Q6InferenceResult,
)
from plugins.nine_questions.q6_what_should_i_not_do.llm_prompt import build_q6_llm_request
QUESTION_REF = "如果我做了会怎样 / 代价与后果是什么"

logger = logging.getLogger(__name__)
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
    run_audit_integration,
    run_learning_integration,
    run_memory_integration,
    run_reflection_integration,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    persist_question_module_output,
    render_human_readable_block,
    render_q4_boundary,
    render_q5_boundary,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)


PROTECTED_EVOLUTION_MODULES = ("安全门", "审计通道", "监督边界", "身份边界")
CONSEQUENCE_SEVERITIES = {"low", "medium", "high"}
REVERSIBILITY_VALUES = {"reversible", "partially_reversible", "irreversible", "unknown"}
BASE_VALIDATION_MARKERS = (
    "lint",
    "test",
    "typecheck",
    "build",
    "sandbox",
    "read_only=true",
    "side_effect_free=true",
    "llm_trace_payload",
    "llm_trace_payload",
    "Human Review",
    "audit approval",
)
FAILURE_2_VALIDATION_MARKERS = (
    "mandatory_replay_regression_suite",
    "adversarial_safety_invariance_check",
    "human_approval_required_before_promotion",
)
FAILURE_3_VALIDATION_MARKERS = (
    "dual_pipeline_reproducibility_gate",
    "strict_shadow_mode_evaluation",
)
MUTATION_TERMS = (
    "改写",
    "修改",
    "覆盖",
    "替换",
    "重构",
    "重载",
    "调整规则",
    "rewrite",
    "modify",
    "replace",
    "refactor",
    "override",
    "patch",
)
HIGH_RISK_CODE_TERMS = ("代码", "code", "patch", "refactor", "rewrite", "modify", "改写", "重构")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _walk_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if any(key in value for key in ("status", "outcome", "result", "error_code")):
            records.append(value)
        for item in value.values():
            records.extend(_walk_records(item))
    elif isinstance(value, list):
        for item in value:
            records.extend(_walk_records(item))
    return records


def _extract_evolution_history(*sources: Any) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("evolution_history", "failure_history", "recent_evolution_outcomes"):
            value = source.get(key)
            if isinstance(value, list):
                history.extend(item for item in value if isinstance(item, dict))
        learning = source.get("learning_history") or source.get("b8_learning_failures")
        if isinstance(learning, (dict, list)):
            history.extend(_walk_records(learning))
    return history[:32]


def _consecutive_evolution_failures(history: list[dict[str, Any]]) -> int:
    failures = 0
    for item in reversed(history):
        status = str(item.get("status") or item.get("outcome") or item.get("result") or "").lower()
        if status in {"failed", "failure", "blocked", "rollback", "rolled_back", "rejected", "失败", "回滚", "拒绝"}:
            failures += 1
            continue
        if status in {"passed", "success", "succeeded", "accepted", "成功", "通过"}:
            break
    return failures


def _contains_marker(items: list[str], marker: str) -> bool:
    needle = marker.lower()
    return any(needle in item.lower() for item in items)


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contains_boundary(items: list[str], required: str) -> bool:
    needle = _normalized_text(required)
    if not needle:
        return True
    return any(needle in _normalized_text(item) for item in items)


def _required_forbidden_boundaries(
    forbidden_zone_baseline: dict[str, Any],
    normalized_global_constraints: list[dict[str, Any]],
) -> list[str]:
    required: list[str] = [
        "绝对禁止演化出绕过人工审核的修改权限",
        "绝对禁止覆盖或重构身份边界",
        "绝对禁止改写安全门禁",
        "绝对禁止绕过审计通道",
        "绝对禁止绕过监督边界",
    ]
    for key in ("absolute_red_lines", "performance_tradeoff_bans", "prohibited_strategies", "contamination_risks"):
        required.extend(_string_list(forbidden_zone_baseline.get(key)))
    for item in normalized_global_constraints:
        required.extend(_string_list(item.get("non_bypassable_constraints")))
        required.extend(_string_list(item.get("contamination_risks")))
    return list(dict.fromkeys(item for item in required if str(item).strip()))


def _mandatory_validation_requirements(consecutive_failures: int) -> list[str]:
    requirements = [
        "lint validation must pass before promotion",
        "test validation must pass before promotion",
        "typecheck validation must pass before promotion",
        "build validation must pass before promotion",
        "sandbox preflight must pass",
        "candidate must declare read_only=true",
        "candidate must declare side_effect_free=true",
        "llm_trace_payload must be persistently recorded",
        "Human Review or audit approval is required before active promotion",
    ]
    if consecutive_failures >= 2:
        requirements.extend(FAILURE_2_VALIDATION_MARKERS)
    if consecutive_failures >= 3:
        requirements.extend(FAILURE_3_VALIDATION_MARKERS)
    return requirements


def _merge_unique_text(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in _string_list(group)))


def _apply_q6_consequence_floor(
    inference: Q6InferenceResult,
    *,
    consecutive_failures: int,
    required_forbidden_boundaries: list[str],
) -> Q6InferenceResult:
    assessment = inference.ConsequenceAssessment
    if consecutive_failures >= 2:
        assessment = assessment.model_copy(update={"consequence_severity": "high"})
    elif consecutive_failures >= 1 and assessment.consequence_severity == "low":
        assessment = assessment.model_copy(update={"consequence_severity": "medium"})

    profile = inference.CostImpactProfile
    profile = profile.model_copy(
        update={
            "security_compliance_impacts": _merge_unique_text(
                profile.security_compliance_impacts,
                required_forbidden_boundaries,
            ),
            "mitigation_requirements": _merge_unique_text(
                profile.mitigation_requirements,
                _mandatory_validation_requirements(consecutive_failures),
            ),
            "stop_conditions": _merge_unique_text(
                profile.stop_conditions,
                required_forbidden_boundaries,
            ),
        }
    )
    return inference.model_copy(update={"ConsequenceAssessment": assessment, "CostImpactProfile": profile})


def _has_forbidden_module_direction(items: list[str], module_name: str) -> bool:
    module_lower = module_name.lower()
    denial_terms = ("不得", "禁止", "不可", "不能", "must not", "forbid", "forbidden", "never")
    return any(
        module_lower in item.lower() and any(term in item.lower() for term in denial_terms)
        for item in items
    )


def _mentions_protected_mutation(items: list[str]) -> bool:
    lowered_items = [item.lower() for item in items]
    for item in lowered_items:
        if any(module.lower() in item for module in PROTECTED_EVOLUTION_MODULES):
            return True
        if any(term in item for term in MUTATION_TERMS) and any(
            protected in item
            for protected in (
                "safety",
                "audit",
                "supervision",
                "identity",
                "权限策略",
                "身份",
                "审计",
                "监督",
                "安全主链",
            )
        ):
            return True
    return False


def _validate_q6_inference(
    inference: Q6InferenceResult,
    *,
    consecutive_failures: int,
    required_forbidden_boundaries: list[str],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    assessment = inference.ConsequenceAssessment
    profile = inference.CostImpactProfile

    if not assessment.action_under_review.strip():
        errors.append({"field": "ConsequenceAssessment.action_under_review", "reason": "must be non-empty"})
    if not assessment.immediate_consequences:
        errors.append({"field": "ConsequenceAssessment.immediate_consequences", "reason": "must contain at least one item"})
    if not assessment.downstream_consequences:
        errors.append({"field": "ConsequenceAssessment.downstream_consequences", "reason": "must contain at least one item"})
    if not profile.operational_costs:
        errors.append({"field": "CostImpactProfile.operational_costs", "reason": "must contain at least one item"})
    if not profile.security_compliance_impacts:
        errors.append({"field": "CostImpactProfile.security_compliance_impacts", "reason": "must contain protected boundary impact evidence"})
    if not profile.user_trust_impacts:
        errors.append({"field": "CostImpactProfile.user_trust_impacts", "reason": "must contain at least one item"})

    impact_and_stop_text = _string_list(profile.security_compliance_impacts) + _string_list(profile.stop_conditions)
    for module_name in PROTECTED_EVOLUTION_MODULES:
        if not any(module_name.lower() in item.lower() for item in impact_and_stop_text):
            errors.append({
                "field": "CostImpactProfile.security_compliance_impacts",
                "reason": f"must explicitly assess impact to {module_name}",
            })
    for required in required_forbidden_boundaries:
        if not _contains_boundary(impact_and_stop_text, required):
            errors.append({
                "field": "CostImpactProfile.security_compliance_impacts",
                "reason": f"must include required boundary as consequence or stop condition: {required}",
            })

    severity = assessment.consequence_severity.strip().lower()
    if severity not in CONSEQUENCE_SEVERITIES:
        errors.append({"field": "ConsequenceAssessment.consequence_severity", "reason": "must be low, medium, or high"})
    if consecutive_failures >= 1 and severity == "low":
        errors.append({"field": "ConsequenceAssessment.consequence_severity", "reason": "continuous failure count >= 1 forbids low"})
    if consecutive_failures >= 2 and severity != "high":
        errors.append({"field": "ConsequenceAssessment.consequence_severity", "reason": "continuous failure count >= 2 requires high"})
    if assessment.reversibility.strip().lower() not in REVERSIBILITY_VALUES:
        errors.append({"field": "ConsequenceAssessment.reversibility", "reason": "must be reversible, partially_reversible, irreversible, or unknown"})

    validation = _string_list(profile.mitigation_requirements)
    if not validation:
        errors.append({"field": "CostImpactProfile.mitigation_requirements", "reason": "must contain strict mitigation and validation gates"})
    for marker in BASE_VALIDATION_MARKERS:
        if not _contains_marker(validation, marker):
            errors.append({"field": "CostImpactProfile.mitigation_requirements", "reason": f"missing required validation marker: {marker}"})
    if consecutive_failures >= 2:
        for marker in FAILURE_2_VALIDATION_MARKERS:
            if not _contains_marker(validation, marker):
                errors.append({"field": "CostImpactProfile.mitigation_requirements", "reason": f"missing continuous-failure validation marker: {marker}"})
    if consecutive_failures >= 3:
        for marker in FAILURE_3_VALIDATION_MARKERS:
            if not (_contains_marker(validation, marker) or _contains_marker(_string_list(profile.stop_conditions), marker)):
                errors.append({"field": "CostImpactProfile.stop_conditions", "reason": f"missing strict convergence stop marker: {marker}"})
    return errors


def _build_q6_repair_prompt(
    *,
    base_prompt: str,
    validation_errors: list[dict[str, str]],
    last_output: Any,
    attempt: int,
) -> str:
    return (
        f"{base_prompt}\n\n"
        "上一次 Q6 LLM 输出未通过强校验，必须重新输出完整 JSON。\n"
        f"retry_attempt={attempt}\n"
        f"validation_error_report={json_safe_payload(validation_errors)}\n"
        f"last_output={json_safe_payload(last_output)}\n"
        "修复要求：只能返回 ConsequenceAssessment、CostImpactProfile 两个顶层键；"
        "不得添加解释文本；必须补齐缺失字段；CostImpactProfile.security_compliance_impacts 必须显式评估 "
        "安全门、审计通道、监督边界、身份边界的影响，并完整继承 validation_error_report 中指出的 required boundaries；"
        "必须包含 lint/test/typecheck/build、sandbox、read_only=true、side_effect_free=true、"
        "llm_trace_payload 持久化、Human Review 或审计批准。"
    )


def _derive_legacy_forbidden_zone(profile: Q6InferenceResult) -> ForbiddenZoneProfile:
    impact = _string_list(profile.CostImpactProfile.security_compliance_impacts)
    stop_conditions = _string_list(profile.CostImpactProfile.stop_conditions)
    validation = _string_list(profile.CostImpactProfile.mitigation_requirements)
    forbidden = _merge_unique_text(impact, stop_conditions)
    return ForbiddenZoneProfile(
        absolute_red_lines=forbidden,
        performance_tradeoff_bans=[
            item for item in forbidden + validation
            if any(token in item.lower() for token in ("audit", "审计", "promotion", "main chain", "main_chain", "晋升", "主链"))
        ],
        prohibited_strategies=[
            item for item in forbidden
            if any(token in item.lower() for token in ("modify", "rewrite", "改写", "覆盖", "绕过", "bypass"))
        ],
        contamination_risks=[
            item for item in forbidden
            if any(token in item.lower() for token in ("identity", "credential", "身份", "凭证", "污染"))
        ],
    )


class Q6WhatShouldINotDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q6
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q6"
    display_name: str = "Q6: What if I do it?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Zentex Cognitive Kernel Phase 6: 如果我做了会怎样 / 代价与后果是什么.

    [LLM MANDATORY]: Guarantees that consequence, cost, reversibility, and mitigation analysis is explicit.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q6_module_runs = bind_module_runs(context, "q6")
        upstream_context = {
            **load_q3_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
            **load_q4_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
            **load_q5_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
        }
        q3_role_profile = upstream_context.get("q3_role_profile")
        q4_profile = upstream_context.get("q4_capability_boundary_profile")
        q5_boundary = upstream_context.get("q5_permission_boundary")
        q5_profile = upstream_context.get("q5_authorization_boundary_profile")
        if not isinstance(q3_role_profile, dict) or not q3_role_profile:
            raise RuntimeError("q6_q3_role_profile_missing")
        if not isinstance(q4_profile, dict) or not q4_profile:
            raise RuntimeError("q6_q4_capability_boundary_missing")
        if not (
            (isinstance(q5_boundary, dict) and q5_boundary)
            or (isinstance(q5_profile, dict) and q5_profile)
        ):
            raise RuntimeError("q6_q5_authorization_boundary_missing")
        
        plugin_service = context.get("plugin_service")
        if plugin_service is None:
            raise RuntimeError("q6_plugin_service_missing")
        redline_hint_run = start_module_run(
            q6_module_runs,
            "q6_redline_hint_chain",
            source="plugins.nine_questions.q6",
        )
        try:
            global_constraints, redline_hints, plugin_runs = collect_external_redline_inputs(
                plugin_service,
                plugin_id=self.plugin_id,
                feature_code=self.feature_code,
                context=context,
            )
        except Exception as exc:
            logger.exception("Q6 functional redline chain failed")
            fail_module_run(
                redline_hint_run,
                error_code="q6_functional_redline_chain_failed",
                error_message=str(exc),
            )
            raise RuntimeError("q6_functional_redline_chain_failed") from exc
        normalized_global_constraints = normalize_redline_inputs(global_constraints)
        normalized_redline_hints = normalize_redline_inputs(redline_hints)
        if not normalized_global_constraints:
            fail_module_run(
                redline_hint_run,
                error_code="q6_global_constraints_missing",
                error_message="Q6 requires live global constraints from functional plugins.",
            )
            raise RuntimeError("q6_global_constraints_missing")
        if not normalized_redline_hints:
            fail_module_run(
                redline_hint_run,
                error_code="q6_redline_hints_missing",
                error_message="Q6 requires live redline hints from functional plugins.",
            )
            raise RuntimeError("q6_redline_hints_missing")
        finish_module_run(redline_hint_run)
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_redline_hint_chain",
            payload={
                "q6_redline_hints": redline_hints,
                "q6_global_constraints_raw": global_constraints,
            },
            status=str(redline_hint_run.get("status") or "completed"),
            output_kind="evidence",
        )
        constraint_source_run = start_module_run(
            q6_module_runs,
            "q6_constraint_source_validation",
            source="plugins.nine_questions.q6",
        )
        finish_module_run(constraint_source_run)
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_constraint_source_validation",
            payload={"q6_global_constraints": normalized_global_constraints},
            status=str(constraint_source_run.get("status") or "completed"),
            output_kind="evidence",
        )
        risk_assessment_run = start_module_run(
            q6_module_runs,
            "q6_risk_assessment",
            source="plugins.nine_questions.q6",
        )
        finish_module_run(risk_assessment_run)
        forbidden_zone_baseline = derive_forbidden_zone_baseline(
            upstream_context,
            normalized_global_constraints,
            normalized_redline_hints,
        )
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_risk_assessment",
            payload={"q6_forbidden_zone_baseline": forbidden_zone_baseline},
            status=str(risk_assessment_run.get("status") or "completed"),
            output_kind="evidence",
        )

        evolution_history = _extract_evolution_history(context, upstream_context)
        consecutive_evolution_failures = _consecutive_evolution_failures(evolution_history)
        llm_request = build_q6_llm_request(
            rendered_q3_role_profile=render_human_readable_block(
                {"q3_role_profile": q3_role_profile, "q3_mission_boundary": upstream_context.get("q3_mission_boundary") or {}},
                heading="Q3 角色与使命画像",
            ),
            normalized_global_constraints=normalized_global_constraints,
            normalized_redline_hints=normalized_redline_hints,
            forbidden_zone_baseline=forbidden_zone_baseline,
            evolution_history=evolution_history,
            consecutive_evolution_failures=consecutive_evolution_failures,
            rendered_q4_boundary=render_q4_boundary(upstream_context),
            rendered_q5_boundary=render_q5_boundary(upstream_context),
            rendered_global_constraints=render_human_readable_block(normalized_global_constraints, heading="全局不可绕过约束"),
            rendered_redline_hints=render_human_readable_block(normalized_redline_hints, heading="场景风险提示"),
            rendered_forbidden_baseline=render_human_readable_block(forbidden_zone_baseline, heading="代价后果基线"),
            rendered_evolution_history=render_human_readable_block(
                {
                    "consecutive_evolution_failures": consecutive_evolution_failures,
                    "evolution_history": evolution_history,
                },
                heading="历史进化表现反馈",
            ),
            q4_capability_boundary=upstream_context.get("q4_capability_boundary_profile"),
            q5_authorization_boundary=upstream_context.get("q5_permission_boundary"),
            q3_role_profile=q3_role_profile,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        # 3. Prepare Metadata & Traceability
        trace_id = str(context.get("trace_id") or f"q6-evolution:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q6_consequence")

        # [MANDATORY] Caller Context Injection
        caller_context = build_caller_context(
            source_module="q6_what_should_i_not_do_plugin",
            invocation_phase="nine_question_q6_consequence_assessment",
            question_ref=QUESTION_REF,
            decision_id=decision_id,
            trace_id=trace_id,
        )

        # 4. Audit Log: Trigger
        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q6_what_should_i_not_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "system_prompt": system_prompt,
                "prompt": prompt,
                "context": model_context,
            },
        )
        forbidden_projection_run = start_module_run(
            q6_module_runs,
            "q6_forbidden_projection",
            source="plugins.nine_questions.q6",
        )

        # 5-6. Execute LLM Inference, Validate, and Retry Invalid Structured Output
        max_retries = int(context.get("q6_max_llm_validation_retries") or 3)
        validation_error_reports: list[dict[str, Any]] = []
        raw: Any = None
        inference: Q6InferenceResult | None = None
        active_prompt = f"{system_prompt}\n\n{prompt}"
        required_forbidden_boundaries = _required_forbidden_boundaries(
            forbidden_zone_baseline,
            normalized_global_constraints,
        )
        for attempt in range(1, max_retries + 1):
            try:
                raw = provider.generate_json(
                    prompt=active_prompt,
                    context={
                        **model_context,
                        "retry_attempt": attempt,
                        "validation_error_reports": validation_error_reports,
                    },
                    caller_context=caller_context,
                )
            except Exception as exc:
                record_model_failed(
                    transcript_store,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="plugins.nine_questions.q6_what_should_i_not_do",
                    payload={
                        "request_id": request_id,
                        "decision_id": decision_id,
                        "question_ref": QUESTION_REF,
                        "caller_context": caller_context.model_dump(mode="json"),
                        "attempt": attempt,
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    },
                )
                fail_module_run(
                    forbidden_projection_run,
                    error_code="q6_llm_invocation_failed",
                    error_message=str(exc),
                )
                raise RuntimeError("q6_llm_invocation_failed") from exc

            try:
                candidate = Q6InferenceResult.model_validate(raw)
            except Exception as exc:
                validation_errors = [{"field": "q6_output_contract", "reason": str(exc)}]
            else:
                candidate = _apply_q6_consequence_floor(
                    candidate,
                    consecutive_failures=consecutive_evolution_failures,
                    required_forbidden_boundaries=required_forbidden_boundaries,
                )
                validation_errors = _validate_q6_inference(
                    candidate,
                    consecutive_failures=consecutive_evolution_failures,
                    required_forbidden_boundaries=required_forbidden_boundaries,
                )
                if not validation_errors:
                    inference = candidate
                    break

            validation_error_reports.append(
                {
                    "attempt": attempt,
                    "errors": validation_errors,
                    "last_output": json_safe_payload(raw),
                }
            )
            active_prompt = _build_q6_repair_prompt(
                base_prompt=f"{system_prompt}\n\n{prompt}",
                validation_errors=validation_errors,
                last_output=raw,
                attempt=attempt + 1,
            )

        if inference is None:
            fail_module_run(
                forbidden_projection_run,
                error_code="q6_output_validation_failed",
                error_message=str(validation_error_reports[-1]["errors"] if validation_error_reports else "unknown validation failure"),
            )
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q6_what_should_i_not_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": "Q6OutputValidationError",
                    "error_message": "q6_output_validation_failed_after_retries",
                    "validation_error_reports": validation_error_reports,
                    "last_output": json_safe_payload(raw),
                },
            )
            raise RuntimeError("q6_output_validation_failed")

        consequence_assessment = inference.ConsequenceAssessment
        cost_impact_profile = inference.CostImpactProfile
        legacy_forbidden_zone_profile = _derive_legacy_forbidden_zone(inference)

        # 7. Audit Log: Completion
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q6_what_should_i_not_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "llm_trace_payload": {
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "system_prompt": system_prompt,
                    "prompt": prompt,
                    "context": model_context,
                    "validation_error_reports": validation_error_reports,
                    "consecutive_evolution_failures": consecutive_evolution_failures,
                },
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
            },
        )

        # 8. Return Cognitive Result
        summary = (
            f"Action={consequence_assessment.action_under_review[:120]}; "
            f"Immediate={len(consequence_assessment.immediate_consequences)}; "
            f"Downstream={len(consequence_assessment.downstream_consequences)}; "
            f"Severity={consequence_assessment.consequence_severity}; "
            f"Reversibility={consequence_assessment.reversibility}"
        )
        finish_module_run(
            forbidden_projection_run,
            status="completed",
        )
        q6_execution_diagnosis = {
            "authenticity_status": "completed",
            "diagnosis_code": "completed",
            "diagnosis_message": "Q6 completed with validated what-if consequence assessment, cost impact profile, and retry-enforced LLM output.",
            "module_runs": list(q6_module_runs),
            "plugin_runs": plugin_runs,
            "upstream_dependencies": [
                {
                    "dependency_id": "q5",
                    "required": True,
                    "status": "completed" if upstream_context.get("q5_permission_boundary") or upstream_context.get("q5_authorization_boundary_profile") else "missing",
                    "message": "Q5 cannot-do boundary constrains Q6 consequence reasoning.",
                }
            ],
            "recovery_plan": build_recovery_plan(
                question_id="q6",
                retriable=True,
                rollback_available=False,
                partial_retry_available=True,
                partial_replace_available=False,
                actions=[
                    build_recovery_action(
                        "q6-rerun-question",
                        label="重跑 Q6 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q6",
                        reason="重新执行代价与后果评估。",
                        path="/api/web/nine-questions/q6/run",
                    ),
                    build_recovery_action(
                        "q6-rerun-upstream-q5",
                        label="先重跑 Q5 再重跑 Q6",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q5->q6",
                        reason="Q6 依赖 Q5 禁止边界与保护约束。",
                        path="/api/web/nine-questions/q5/run",
                    ),
                    build_recovery_action(
                        "q6-refresh-redline-plugins",
                        label="刷新风险插件输入",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q6_redline_hint_chain",
                        reason="仅刷新 Q6 redline functional inputs 和基线，不重跑 LLM。",
                        path="/api/web/nine-questions/q6/modules/q6_redline_hint_chain/retry",
                    ),
                ],
            ),
        }
        q6_payload = inference.model_dump(mode="json")
        q6_legacy_payload = legacy_forbidden_zone_profile.model_dump(mode="json")
        llm_trace_payload = {
            "request_id": request_id,
            "decision_id": decision_id,
            "provider_name": safe_provider_plugin_id(provider),
            "model": json_safe_payload(getattr(provider, "last_model_name", None)),
            "question_ref": QUESTION_REF,
            "system_prompt": system_prompt,
            "prompt": prompt,
            "source_module": caller_context.source_module,
            "invocation_phase": caller_context.invocation_phase,
            "context_data": model_context,
            "result": q6_payload,
            "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
            "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            "validation_error_reports": validation_error_reports,
            "consecutive_evolution_failures": consecutive_evolution_failures,
        }
        llm_trace_payload["invocations"] = [dict(llm_trace_payload)]
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_consequence_projection",
            payload={
                **q6_payload,
                "llm_trace_payload": llm_trace_payload,
            },
            status=str(forbidden_projection_run.get("status") or "completed"),
            output_kind="inference",
        )
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_forbidden_projection",
            payload={
                **q6_legacy_payload,
                "llm_trace_payload": llm_trace_payload,
            },
            status=str(forbidden_projection_run.get("status") or "completed"),
            output_kind="inference",
        )
        q6_module_runs = q6_execution_diagnosis.get("module_runs")
        q6_module_runs = q6_module_runs if isinstance(q6_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            summary="Q6 代价与后果画像与 LLM 校验轨迹已记录。",
            payload={
                "q6_consequence_assessment": consequence_assessment.model_dump(mode="json"),
                "q6_cost_impact_profile": cost_impact_profile.model_dump(mode="json"),
                "q6_consequence_inference": q6_payload,
                "q6_forbidden_zone_profile": q6_legacy_payload,
                "q6_global_constraints": normalized_global_constraints,
                "q6_redline_hints": normalized_redline_hints,
                "llm_trace_payload": llm_trace_payload,
            },
        )
        run_memory_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            title="Q6 Consequence Profile",
            summary="Q6 代价与后果画像已写入记忆。",
            layer="episodic",
            payload=q6_payload,
            tags=["nine-questions", "q6", "consequence-profile"],
        )
        run_reflection_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            subject="Q6 consequence assessment",
            summary="Q6 代价、后果、缓解条件与停止条件反思已记录。",
            reflection_type="error_reflection",
            payload={
                "q6_consequence_assessment": consequence_assessment.model_dump(mode="json"),
                "q6_cost_impact_profile": cost_impact_profile.model_dump(mode="json"),
                "q6_consequence_inference": q6_payload,
                "q6_forbidden_zone_profile": q6_legacy_payload,
                "q6_redline_hints": normalized_redline_hints,
            },
        )
        run_learning_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            learning_kind="consequence_assessment",
            summary="Q6 代价与后果学习记录已登记。",
            payload=q6_payload,
        )
        q6_execution_diagnosis["module_runs"] = q6_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "consequence_assessment",
                    **consequence_assessment.model_dump(mode="json"),
                },
                {
                    "kind": "cost_impact_profile",
                    **cost_impact_profile.model_dump(mode="json"),
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q6_consequence_assessment": consequence_assessment.model_dump(mode="json"),
                "q6_cost_impact_profile": cost_impact_profile.model_dump(mode="json"),
                "q6_consequence_inference": q6_payload,
                "q6_llm_validation_error_reports": validation_error_reports,
                "q6_consecutive_evolution_failures": consecutive_evolution_failures,
                "q6_forbidden_zone_profile": q6_legacy_payload,
                "q6_global_constraints": normalized_global_constraints,
                "q6_redline_hints": normalized_redline_hints,
                "q6_forbidden_zone_baseline": forbidden_zone_baseline,
                "q6_execution_diagnosis": q6_execution_diagnosis,
                "llm_trace_payload": llm_trace_payload,
            },
            llm_trace_payload=llm_trace_payload,
            confidence=0.95,
        )


def build_q6_what_should_i_not_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q6,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q6WhatShouldINotDoPlugin:
    return Q6WhatShouldINotDoPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q6",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
