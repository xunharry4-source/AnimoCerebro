from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_ids import NINE_QUESTION_Q7
from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

from zentex.common.cognitive_result import CognitiveToolResult
from plugins.nine_questions.q7_what_else_can_i_do.llm_prompt import build_q7_llm_request
from plugins.nine_questions.q7_what_else_can_i_do.modules import (
    build_q7_baseline_modules,
    derive_alternative_strategy_baseline,
    merge_with_strategy_baseline,
    normalize_functional_alternatives,
)
from plugins.nine_questions.q7_what_else_can_i_do.models import Q7InferenceResult
from zentex.common.nine_questions_shared import (
    build_nine_question_partial_failure,
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
    run_audit_integration,
    run_learning_integration,
    load_authoritative_question_context_from_storage,
    run_memory_integration,
    run_reflection_integration,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    json_safe_payload,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_human_readable_block,
    render_q4_boundary,
    render_q5_boundary,
    render_q6_redlines,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)


def _normalize_text_set(values: list[Any]) -> set[str]:
    normalized: set[str] = set()
    for item in values:
        text = str(item or "").strip().lower()
        if text:
            normalized.add(text)
    return normalized


def _classify_fallback_plans(
    fallback_plans: list[str],
    *,
    q4_profile: dict[str, Any],
    q5_profile: dict[str, Any],
    q6_profile: dict[str, Any],
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    actionable_space = _normalize_text_set(list(q4_profile.get("actionable_space") or []))
    capability_limits = _normalize_text_set(list(q4_profile.get("capability_upper_limits") or []))

    forbidden_actions = []
    for item in list(q5_profile.get("forbidden_action_space") or []):
        if isinstance(item, dict):
            action = str(item.get("action") or "").strip()
            if action:
                forbidden_actions.append(action)
    forbidden_actions.extend(list(q5_profile.get("unauthorized_actions") or []))
    forbidden_actions.extend(list(q5_profile.get("conditional_actions") or []))
    forbidden_set = _normalize_text_set(forbidden_actions)

    redline_set = _normalize_text_set(list(q6_profile.get("absolute_red_lines") or []))
    redline_set.update(_normalize_text_set(list(q6_profile.get("prohibited_strategies") or [])))

    validated: list[str] = []
    unverified: list[str] = []
    rejected: list[dict[str, str]] = []

    for raw in fallback_plans:
        plan = str(raw or "").strip()
        if not plan:
            continue
        lowered = plan.lower()

        rejection_reason = ""
        for blocked in forbidden_set:
            if blocked and blocked in lowered:
                rejection_reason = f"violates_q5_forbidden:{blocked}"
                break
        if not rejection_reason:
            for blocked in redline_set:
                if blocked and blocked in lowered:
                    rejection_reason = f"violates_q6_redline:{blocked}"
                    break
        if not rejection_reason:
            for blocked in capability_limits:
                if blocked and blocked in lowered:
                    rejection_reason = f"hits_q4_capability_limit:{blocked}"
                    break

        if rejection_reason:
            rejected.append({"plan": plan, "reason": rejection_reason})
            continue

        if len(lowered) < 8:
            unverified.append(plan)
            continue
        if actionable_space and any(token in lowered for token in actionable_space):
            validated.append(plan)
            continue
        validated.append(plan)

    return validated, unverified, rejected

QUESTION_REF = "我还可以做什么"


class WhatElseCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q7
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q7"
    display_name: str = "Q7: What else can I do?"
    description: str = "Generate fallback strategies and substitute actions."
    behavior_key: str = "q7_alternative_strategy"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["unhandled_q7_failure"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q7_module_runs = bind_module_runs(context, "q7")
        upstream_context = load_authoritative_question_context_from_storage(context, ["q3", "q4", "q5", "q6"])

        # 1. 从 authoritative question_snapshots 提取 Q3-Q6 数据
        q4_profile = upstream_context.get("q4_capability_boundary_profile") or {}
        q5_profile = upstream_context.get("q5_authorization_boundary_profile") or upstream_context.get("q5_permission_boundary") or {}
        q6_profile = upstream_context.get("q6_forbidden_zone_profile") or {}
        q3_eval = upstream_context.get("q3_resource_evaluation") or {}
        dependency_validation_run = start_module_run(
            q7_module_runs,
            "q7_dependency_validation",
            source="plugins.nine_questions.q7",
        )
        finish_module_run(
            dependency_validation_run,
            status="completed" if q3_eval and q4_profile and q5_profile and q6_profile else "degraded",
            error_code="" if q3_eval and q4_profile and q5_profile and q6_profile else "upstream_dependency_degraded",
            error_message="" if q3_eval and q4_profile and q5_profile and q6_profile else "One or more upstream profiles are missing or degraded.",
        )
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_dependency_validation",
            payload={
                "q3_resource_evaluation": q3_eval,
                "q4_capability_boundary_profile": q4_profile,
                "q5_authorization_boundary_profile": q5_profile,
                "q6_forbidden_zone_profile": q6_profile,
            },
            status=str(dependency_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )

        # 2. 执行 functional plugins（保留原有逻辑）
        plugin_service = context.get("plugin_service")
        raw_inputs: list[dict[str, Any]] = []
        functional_alternatives: list[dict[str, Any]] = []
        plugin_runs: list[dict[str, Any]] = []
        functional_chain_run = start_module_run(
            q7_module_runs,
            "q7_functional_alternative_chain",
            source="plugins.nine_questions.q7",
        )
        if plugin_service is not None:
            try:
                raw_inputs = execute_enabled_cognitive_plugin_functionals(
                    plugin_service,
                    self.plugin_id,
                    default_parameters={"block_context": dict(context)},
                    trace_id=str(context.get("trace_id") or "q7"),
                    originator_id=str(context.get("session_id") or "unknown-session"),
                    caller_plugin_id=self.plugin_id,
                )
                for item in raw_inputs:
                    plugin_runs.append(
                        {
                            "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                            "feature_code": str(item.get("feature_code") or self.feature_code),
                            "expected": True,
                            "attempted": True,
                            "status": "completed" if item.get("status") == "done" else "failed",
                            "error_code": "" if item.get("status") == "done" else "alternative_plugin_failed",
                            "error_message": "" if item.get("status") == "done" else str(item.get("error") or "alternative strategy plugin failed"),
                            "duration_ms": 0,
                            "input_summary": {},
                            "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
                        }
                    )
                functional_alternatives = [
                    item.get("result")
                    for item in raw_inputs
                    if item.get("status") == "done" and item.get("result")
                ]
                finish_module_run(
                    functional_chain_run,
                    status="completed" if raw_inputs else "ready",
                    error_code="",
                    error_message=(
                        ""
                        if raw_inputs
                        else "No functional alternative plugins executed; proceeding with upstream-only baseline alternatives."
                    ),
                )
            except Exception as exc:
                # 严禁吞掉 functional chain 异常然后继续产出“看似正常”的 Q7 结果。
                # 这会把后台真实故障伪装成普通降级，严重破坏系统稳定性与审计可信度。
                logger.exception("Q7 functional alternative chain failed")
                fail_module_run(
                    functional_chain_run,
                    error_code="q7_functional_alternative_chain_failed",
                    error_message=str(exc),
                )
                return build_nine_question_partial_failure(
                    context=context,
                    tool_id=self.plugin_id,
                    question_id="q7",
                    question_ref=QUESTION_REF,
                    error_code="q7_functional_alternative_chain_failed",
                    error_message=str(exc),
                    diagnosis_key="q7_execution_diagnosis",
                    module_runs=list(q7_module_runs),
                    plugin_runs=plugin_runs,
                    upstream_dependencies=[
                        {"dependency_id": "q4", "required": True, "status": "completed" if q4_profile else "missing"},
                        {"dependency_id": "q5", "required": True, "status": "completed" if q5_profile else "missing"},
                        {"dependency_id": "q6", "required": True, "status": "completed" if q6_profile else "missing"},
                    ],
                    context_updates={},
                    required_modules=["q7_functional_alternative_chain"],
                )
        else:
            finish_module_run(
                functional_chain_run,
                status="missing",
                error_code="plugin_service_missing",
                error_message="Functional alternative chain not started.",
            )
        normalized_functional_alternatives = normalize_functional_alternatives(functional_alternatives)
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_functional_alternative_chain",
            payload={"q7_functional_alternatives": normalized_functional_alternatives},
            status=str(functional_chain_run.get("status") or "completed"),
            output_kind="evidence",
        )
        alternative_strategy_baseline = derive_alternative_strategy_baseline(
            upstream_context,
            normalized_functional_alternatives,
        )
        q7_module_results = build_q7_baseline_modules(upstream_context, normalized_functional_alternatives)
        fallback_baseline_run = start_module_run(
            q7_module_runs,
            "q7_fallback_baseline_projection",
            source="plugins.nine_questions.q7",
        )
        finish_module_run(fallback_baseline_run, status="completed")
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_fallback_baseline_projection",
            payload=alternative_strategy_baseline,
            status=str(fallback_baseline_run.get("status") or "completed"),
            output_kind="evidence",
        )

        llm_request = build_q7_llm_request(
            rendered_q4_boundary=render_q4_boundary(upstream_context),
            rendered_q5_boundary=render_q5_boundary(upstream_context),
            rendered_q6_redlines=render_q6_redlines(upstream_context),
            rendered_q3_resource_state=render_human_readable_block(q3_eval, heading="Q3 资源状态"),
            rendered_functional_alternatives=render_human_readable_block(normalized_functional_alternatives, heading="插件建议备选策略"),
            rendered_strategy_baseline=render_human_readable_block(alternative_strategy_baseline, heading="备选策略基线"),
            q4_capability_boundary=q4_profile,
            q5_authorization_boundary=q5_profile,
            q6_forbidden_zone=q6_profile,
            q3_resource_evaluation=q3_eval,
            functional_alternatives=normalized_functional_alternatives,
            alternative_strategy_baseline=alternative_strategy_baseline,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]

        # 5. 构建追踪元数据
        trace_id = str(context.get("trace_id") or f"q7-alternatives:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q7_alternatives")

        caller_context = build_caller_context(
            source_module="q7_what_else_can_i_do_plugin",
            invocation_phase="nine_question_q7_alternatives",
            question_ref=QUESTION_REF,
            decision_id=decision_id,
            trace_id=trace_id,
        )

        model_context = llm_request["model_context"]

        # 6. 审计日志：触发
        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q7_what_else_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
            },
        )
        alternative_projection_run = start_module_run(
            q7_module_runs,
            "q7_alternative_projection",
            source="plugins.nine_questions.q7",
        )

        # 7. LLM 调用（Fail-Closed）
        try:
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            # 严禁吞掉 Q7 LLM 调用异常并只返回 partial_failed。
            # 这里必须保留异常堆栈，否则后台替代策略推理故障会被隐藏成普通失败。
            logger.exception("Q7 LLM invocation failed")
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q7_what_else_can_i_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            fail_module_run(
                alternative_projection_run,
                error_code="q7_llm_invocation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q7",
                question_ref=QUESTION_REF,
                error_code="q7_llm_invocation_failed",
                error_message=str(exc),
                diagnosis_key="q7_execution_diagnosis",
                module_runs=list(q7_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[],
                context_updates={
                    "q7_functional_alternatives": normalized_functional_alternatives,
                    "q7_alternative_strategy_baseline": alternative_strategy_baseline,
                },
                required_modules=["q7_alternative_projection"],
            )

        # 8. Pydantic 验证
        try:
            inference = Q7InferenceResult.model_validate(raw)
        except Exception as exc:
            # 严禁吞掉 Q7 输出校验异常并假装只是常规失败。
            # 校验失败必须留下异常日志，避免功能假实现继续污染后续链路。
            logger.exception("Q7 output validation failed")
            fail_module_run(
                alternative_projection_run,
                error_code="q7_output_validation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q7",
                question_ref=QUESTION_REF,
                error_code="q7_output_validation_failed",
                error_message=str(exc),
                diagnosis_key="q7_execution_diagnosis",
                module_runs=list(q7_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[],
                context_updates={
                    "q7_functional_alternatives": normalized_functional_alternatives,
                    "q7_alternative_strategy_baseline": alternative_strategy_baseline,
                },
                required_modules=["q7_alternative_projection"],
            )
        inferred_profile = inference.alternative_strategy_profile
        profile = inferred_profile.model_copy(
            update={
                "fallback_plans": merge_with_strategy_baseline(
                    inferred_profile.fallback_plans,
                    alternative_strategy_baseline.get("fallback_plans", []),
                ),
                "degradation_strategies": merge_with_strategy_baseline(
                    inferred_profile.degradation_strategies,
                    alternative_strategy_baseline.get("degradation_strategies", []),
                ),
                "collaboration_switches": merge_with_strategy_baseline(
                    inferred_profile.collaboration_switches,
                    alternative_strategy_baseline.get("collaboration_switches", []),
                ),
                "exploratory_actions": merge_with_strategy_baseline(
                    inferred_profile.exploratory_actions,
                    alternative_strategy_baseline.get("exploratory_actions", []),
                ),
            }
        )

        # 9. 审计日志：完成
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q7_what_else_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "result": inference.model_dump(mode="json"),
            },
        )

        # 10. 返回 CognitiveToolResult
        summary = (
            f"fallbacks={len(profile.fallback_plans)}; "
            f"degradations={len(profile.degradation_strategies)}; "
            f"collaborations={len(profile.collaboration_switches)}"
        )
        validated_fallbacks, unverified_fallbacks, rejected_fallbacks = _classify_fallback_plans(
            list(profile.fallback_plans or []),
            q4_profile=q4_profile,
            q5_profile=q5_profile if isinstance(q5_profile, dict) else {},
            q6_profile=q6_profile if isinstance(q6_profile, dict) else {},
        )
        feasibility_validation_run = start_module_run(
            q7_module_runs,
            "q7_feasibility_validation",
            source="plugins.nine_questions.q7",
        )
        finish_module_run(
            feasibility_validation_run,
            status="completed" if validated_fallbacks else "degraded",
            error_code="" if validated_fallbacks else "feasibility_validation_unverified",
            error_message=(
                ""
                if validated_fallbacks
                else "No fallback plan passed Q4/Q5/Q6 feasibility validation."
            ),
        )
        authenticity_status = (
            "completed"
            if plugin_service is not None and q4_profile and q5_profile and q6_profile and len(validated_fallbacks) > 0
            else "degraded"
        )
        finish_module_run(alternative_projection_run, status="completed")
        q7_execution_diagnosis = {
            "authenticity_status": authenticity_status,
            "diagnosis_code": "alternative_strategy_degraded" if authenticity_status != "completed" else "completed",
            "diagnosis_message": (
                "Q7 generated alternative strategies, but feasibility validation is still incomplete; suggestions remain unverified."
                if authenticity_status != "completed"
                else "Q7 completed with validated alternative strategies."
            ),
            "used_fallback": authenticity_status != "completed",
            "upstream_degraded": not bool(q4_profile and q5_profile and q6_profile),
            "module_runs": list(q7_module_runs),
            "plugin_runs": plugin_runs,
            "upstream_dependencies": [
                {
                    "dependency_id": "q4",
                    "required": True,
                    "status": "completed" if q4_profile else "missing",
                    "message": "Q4 capability boundary constrains Q7 alternatives.",
                },
                {
                    "dependency_id": "q5",
                    "required": True,
                    "status": "completed" if q5_profile else "missing",
                    "message": "Q5 authorization boundary constrains Q7 alternatives.",
                },
                {
                    "dependency_id": "q6",
                    "required": True,
                    "status": "completed" if q6_profile else "missing",
                    "message": "Q6 forbidden-zone boundary constrains Q7 alternatives.",
                },
            ],
            "recovery_plan": build_recovery_plan(
                question_id="q7",
                retriable=True,
                rollback_available=False,
                partial_retry_available=True,
                partial_replace_available=False,
                actions=[
                    build_recovery_action(
                        "q7-rerun-question",
                        label="重跑 Q7 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q7",
                        reason="重新执行替代策略推导。",
                        path="/api/web/nine-questions/q7/run",
                    ),
                    build_recovery_action(
                        "q7-rerun-upstream-q4-q6",
                        label="先重跑 Q4-Q6 再重跑 Q7",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q4,q5,q6->q7",
                        reason="Q7 依赖能力、授权和红线边界。",
                        path="/api/web/nine-questions/q4/run",
                    ),
                    build_recovery_action(
                        "q7-refresh-functional-alternatives",
                        label="刷新备选策略插件输入",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q7_functional_alternative_chain",
                        reason="仅刷新 Q7 functional alternative inputs 与基线，不重跑 LLM。",
                        path="/api/web/nine-questions/q7/modules/q7_functional_alternative_chain/retry",
                    ),
                    build_recovery_action(
                        "q7-validate-fallbacks",
                        label="对 fallback 做可行性验证",
                        kind="partial_replace",
                        executable=False,
                        scope="feasibility_validation",
                        target="validated_fallbacks",
                        reason="真实可行性验证器尚未落地，当前只输出未验证建议。",
                    ),
                ],
            ),
            "projection_summary": {
                "validated_fallbacks": validated_fallbacks,
                "unverified_fallbacks": unverified_fallbacks,
                "rejected_fallbacks": rejected_fallbacks,
            },
        }
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_alternative_projection",
            payload=profile.model_dump(mode="json"),
            status=str(alternative_projection_run.get("status") or "completed"),
            output_kind="inference",
        )
        q7_module_runs = q7_execution_diagnosis.get("module_runs")
        q7_module_runs = q7_module_runs if isinstance(q7_module_runs, list) else []
        q7_payload = profile.model_dump(mode="json")
        run_audit_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            summary="Q7 备选策略链审计已记录。",
            payload={
                "q7_alternative_strategy_profile": q7_payload,
                "q7_resource_bottlenecks": q7_module_results["resource_bottleneck_projection"]["resource_bottlenecks"],
                "q7_capability_limits": q7_module_results["capability_limit_projection"]["capability_limits"],
                "q7_permission_boundaries": q7_module_results["permission_boundary_projection"]["permission_boundaries"],
                "q7_absolute_red_lines": q7_module_results["absolute_redline_projection"]["absolute_red_lines"],
            },
        )
        run_memory_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            title="Q7 Alternative Strategy",
            summary="Q7 替代策略与失败补丁已写入记忆。",
            layer="episodic",
            payload=q7_payload,
            tags=["nine-questions", "q7", "alternative-strategy"],
        )
        run_reflection_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            subject="Q7 fallback strategy",
            summary="Q7 fallback 有效性反思已记录。",
            reflection_type="strategy_reflection",
            payload={
                "q7_alternative_strategy_profile": q7_payload,
                "q7_historical_failure_patches": q7_module_results["historical_failure_patch_projection"]["historical_failure_patches"],
            },
        )
        run_learning_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            learning_kind="alternative_strategy",
            summary="Q7 替代策略学习记录已登记。",
            payload=q7_payload,
        )
        q7_execution_diagnosis["module_runs"] = q7_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[{"kind": "alternative_strategy_profile", **profile.model_dump(mode="json")}],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q7_module_results": q7_module_results,
                "q7_alternative_strategy_profile": profile.model_dump(mode="json"),
                "q7_functional_alternatives": normalized_functional_alternatives,
                "q7_alternative_strategy_baseline": alternative_strategy_baseline,
                "q7_resource_bottlenecks": q7_module_results["resource_bottleneck_projection"]["resource_bottlenecks"],
                "q7_capability_limits": q7_module_results["capability_limit_projection"]["capability_limits"],
                "q7_permission_boundaries": q7_module_results["permission_boundary_projection"]["permission_boundaries"],
                "q7_absolute_red_lines": q7_module_results["absolute_redline_projection"]["absolute_red_lines"],
                "q7_historical_failure_patches": q7_module_results["historical_failure_patch_projection"]["historical_failure_patches"],
                "q7_execution_diagnosis": q7_execution_diagnosis,
            },
            confidence=0.7,
        )


def build_q7_what_else_can_i_do_plugin() -> WhatElseCanIDoPlugin:
    return WhatElseCanIDoPlugin()
