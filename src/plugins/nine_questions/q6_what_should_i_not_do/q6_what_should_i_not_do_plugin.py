from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q6
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q6_what_should_i_not_do.modules import (
    derive_forbidden_zone_baseline,
    merge_with_forbidden_baseline,
    normalize_redline_inputs,
)
from plugins.nine_questions.q6_what_should_i_not_do.models import Q6InferenceResult
from plugins.nine_questions.q6_what_should_i_not_do.llm_prompt import build_q6_llm_request
# Decoupled: Inputs come from identity constraint and red-line plugins
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


QUESTION_REF = "我即使能做也不该做什么"

logger = logging.getLogger(__name__)
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
    build_model_context,
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


class Q6WhatShouldINotDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q6
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q6"
    display_name: str = "Q6: What should I not do?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Zentex Cognitive Kernel Phase 6: 我即使能做也不该做什么 (Q6: Moral & Strategic Redlines).

    [LLM MANDATORY]: Guarantees that the forbidden zone is a semantic, non-bypassable deduction.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q6_module_runs = bind_module_runs(context, "q6")
        upstream_context = load_authoritative_question_context_from_storage(context, ["q4", "q5"])
        
        global_constraints: list[dict[str, Any]] = []
        redline_hints: list[list[dict[str, Any]] | dict[str, Any]] = []
        plugin_runs: list[dict[str, Any]] = []
        plugin_service = context.get("plugin_service")
        redline_hint_run = start_module_run(
            q6_module_runs,
            "q6_redline_hint_chain",
            source="plugins.nine_questions.q6",
        )
        if plugin_service is not None:
            try:
                functional_inputs = execute_enabled_cognitive_plugin_functionals(
                    plugin_service,
                    self.plugin_id,
                    default_parameters=dict(context),
                    trace_id=str(context.get("trace_id") or "q6"),
                    originator_id=str(context.get("session_id") or "unknown-session"),
                    caller_plugin_id=self.plugin_id,
                )
                for item in functional_inputs:
                    plugin_runs.append(
                        {
                            "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                            "feature_code": str(item.get("feature_code") or self.feature_code),
                            "expected": True,
                            "attempted": True,
                            "status": "completed" if item.get("status") == "done" else "failed",
                            "error_code": "" if item.get("status") == "done" else "redline_plugin_failed",
                            "error_message": "" if item.get("status") == "done" else str(item.get("error") or "redline plugin failed"),
                            "duration_ms": 0,
                            "input_summary": {},
                            "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
                        }
                    )
                    if item.get("status") != "done":
                        continue
                    result = item.get("result")
                    if not isinstance(result, (dict, list)):
                        continue
                    
                    if isinstance(result, dict):
                        is_redline_pack = (result.get("pack_type") == "redline_pack")
                        has_constraints = "non_bypassable_constraints" in result
                        
                        if is_redline_pack or has_constraints:
                            global_constraints.append(result)
                        elif "zone" in result or "forbidden_actions" in result:
                            redline_hints.append(result)
                    else:
                        # List of hints
                        redline_hints.extend(result)
                has_live_redline_inputs = bool(redline_hints or global_constraints)
                finish_module_run(
                    redline_hint_run,
                    status="completed" if has_live_redline_inputs else "missing",
                    error_code="" if has_live_redline_inputs else "redline_hint_missing",
                    error_message=(
                        ""
                        if has_live_redline_inputs
                        else "No live redline hints or global constraints were produced."
                    ),
                )
            except Exception as exc:
                logger.error(f"Red-line Discovery Failure: {exc}")
                fail_module_run(
                    redline_hint_run,
                    error_code="q6_functional_redline_chain_failed",
                    error_message=str(exc),
                )
                return build_nine_question_partial_failure(
                    context=context,
                    tool_id=self.plugin_id,
                    question_id="q6",
                    question_ref=QUESTION_REF,
                    error_code="q6_functional_redline_chain_failed",
                    error_message=str(exc),
                    diagnosis_key="q6_execution_diagnosis",
                    module_runs=list(q6_module_runs),
                    plugin_runs=plugin_runs,
                    upstream_dependencies=[],
                    context_updates={},
                    required_modules=["q6_redline_hint_chain"],
                )
        else:
            finish_module_run(
                redline_hint_run,
                status="missing",
                error_code="plugin_service_missing",
                error_message="Functional redline chain not started.",
            )
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
        normalized_global_constraints = normalize_redline_inputs(global_constraints)
        normalized_redline_hints = normalize_redline_inputs(redline_hints)
        constraint_source_run = start_module_run(
            q6_module_runs,
            "q6_constraint_source_validation",
            source="plugins.nine_questions.q6",
        )
        finish_module_run(
            constraint_source_run,
            status="completed" if normalized_global_constraints else "degraded",
            error_code="" if normalized_global_constraints else "constraint_snapshot_only",
            error_message="" if normalized_global_constraints else "Global constraints were not validated from live plugin sources.",
        )
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
        finish_module_run(
            risk_assessment_run,
            status="completed" if normalized_global_constraints or normalized_redline_hints else "degraded",
            error_code="" if normalized_global_constraints or normalized_redline_hints else "dynamic_risk_unverified",
            error_message="" if normalized_global_constraints or normalized_redline_hints else "Dynamic risk assessment is inferred from baseline only.",
        )
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

        llm_request = build_q6_llm_request(
            normalized_global_constraints=normalized_global_constraints,
            normalized_redline_hints=normalized_redline_hints,
            forbidden_zone_baseline=forbidden_zone_baseline,
            rendered_q4_boundary=render_q4_boundary(upstream_context),
            rendered_q5_boundary=render_q5_boundary(upstream_context),
            rendered_global_constraints=render_human_readable_block(normalized_global_constraints, heading="全局不可绕过约束"),
            rendered_redline_hints=render_human_readable_block(normalized_redline_hints, heading="场景红线提示"),
            rendered_forbidden_baseline=render_human_readable_block(forbidden_zone_baseline, heading="禁区基线"),
            q4_capability_boundary=upstream_context.get("q4_capability_boundary_profile"),
            q5_authorization_boundary=upstream_context.get("q5_permission_boundary"),
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        # 3. Prepare Metadata & Traceability
        trace_id = str(context.get("trace_id") or f"q6-redline:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q6_redline")

        # [MANDATORY] Caller Context Injection
        caller_context = build_caller_context(
            source_module="q6_what_should_i_not_do_plugin",
            invocation_phase="nine_question_q6_redline",
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

        # 5. Execute LLM Inference with Fail-Closed Block
        try:
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context
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
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            fail_module_run(
                forbidden_projection_run,
                error_code="q6_llm_invocation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q6",
                question_ref=QUESTION_REF,
                error_code="q6_llm_invocation_failed",
                error_message=str(exc),
                diagnosis_key="q6_execution_diagnosis",
                module_runs=list(q6_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[],
                context_updates={
                    "q6_global_constraints": normalized_global_constraints,
                    "q6_redline_hints": normalized_redline_hints,
                    "q6_forbidden_zone_baseline": forbidden_zone_baseline,
                },
                required_modules=["q6_forbidden_projection"],
            )

        # 6. Validate & Parse (Pydantic v2)
        try:
            inference = Q6InferenceResult.model_validate(raw)
        except Exception as exc:
            fail_module_run(
                forbidden_projection_run,
                error_code="q6_output_validation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q6",
                question_ref=QUESTION_REF,
                error_code="q6_output_validation_failed",
                error_message=str(exc),
                diagnosis_key="q6_execution_diagnosis",
                module_runs=list(q6_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[],
                context_updates={
                    "q6_global_constraints": normalized_global_constraints,
                    "q6_redline_hints": normalized_redline_hints,
                    "q6_forbidden_zone_baseline": forbidden_zone_baseline,
                },
                required_modules=["q6_forbidden_projection"],
            )
        profile = inference.forbidden_zone_profile
        profile.absolute_red_lines = merge_with_forbidden_baseline(
            profile.absolute_red_lines,
            forbidden_zone_baseline.get("absolute_red_lines", []),
        )
        profile.performance_tradeoff_bans = merge_with_forbidden_baseline(
            profile.performance_tradeoff_bans,
            forbidden_zone_baseline.get("performance_tradeoff_bans", []),
        )
        profile.prohibited_strategies = merge_with_forbidden_baseline(
            profile.prohibited_strategies,
            forbidden_zone_baseline.get("prohibited_strategies", []),
        )
        profile.contamination_risks = merge_with_forbidden_baseline(
            profile.contamination_risks,
            forbidden_zone_baseline.get("contamination_risks", []),
        )

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
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
            },
        )

        # 8. Return Cognitive Result
        summary = (
            f"Redlines={len(profile.absolute_red_lines)}; "
            f"TradeoffBans={len(profile.performance_tradeoff_bans)}; "
            f"Prohibited={len(profile.prohibited_strategies)}"
        )
        authenticity_status = (
            "completed"
            if plugin_service is not None and (normalized_global_constraints or normalized_redline_hints)
            else "degraded"
        )
        finish_module_run(
            forbidden_projection_run,
            status="completed",
        )
        q6_execution_diagnosis = {
            "authenticity_status": authenticity_status,
            "diagnosis_code": "forbidden_zone_degraded" if authenticity_status != "completed" else "completed",
            "diagnosis_message": (
                "Q6 currently relies on static baseline only; dynamic risk and redline plugin evidence is incomplete."
                if authenticity_status != "completed"
                else "Q6 completed with validated constraint and redline plugin evidence."
            ),
            "used_fallback": authenticity_status != "completed",
            "upstream_degraded": False,
            "module_runs": list(q6_module_runs),
            "plugin_runs": plugin_runs,
            "upstream_dependencies": [
                {
                    "dependency_id": "q5",
                    "required": True,
                    "status": "completed" if upstream_context.get("q5_permission_boundary") or upstream_context.get("q5_authorization_boundary_profile") else "missing",
                    "message": "Q5 authorization boundary constrains Q6 forbidden-zone reasoning.",
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
                        reason="重新执行禁区与红线判断。",
                        path="/api/web/nine-questions/q6/run",
                    ),
                    build_recovery_action(
                        "q6-rerun-upstream-q5",
                        label="先重跑 Q5 再重跑 Q6",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q5->q6",
                        reason="Q6 依赖 Q5 授权边界。",
                        path="/api/web/nine-questions/q5/run",
                    ),
                    build_recovery_action(
                        "q6-refresh-redline-plugins",
                        label="刷新红线插件输入",
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
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_forbidden_projection",
            payload=profile.model_dump(mode="json"),
            status=str(forbidden_projection_run.get("status") or "completed"),
            output_kind="inference",
        )
        q6_module_runs = q6_execution_diagnosis.get("module_runs")
        q6_module_runs = q6_module_runs if isinstance(q6_module_runs, list) else []
        q6_payload = profile.model_dump(mode="json")
        run_audit_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            summary="Q6 红线与禁区审计已记录。",
            payload={
                "q6_forbidden_zone_profile": q6_payload,
                "q6_global_constraints": normalized_global_constraints,
                "q6_redline_hints": normalized_redline_hints,
            },
        )
        run_memory_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            title="Q6 Forbidden Zone",
            summary="Q6 红线禁区已写入记忆。",
            layer="episodic",
            payload=q6_payload,
            tags=["nine-questions", "q6", "forbidden-zone"],
        )
        run_reflection_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            subject="Q6 forbidden zone",
            summary="Q6 红线覆盖与风险识别反思已记录。",
            reflection_type="error_reflection",
            payload={
                "q6_forbidden_zone_profile": q6_payload,
                "q6_redline_hints": normalized_redline_hints,
            },
        )
        run_learning_integration(
            context,
            question_id="q6",
            module_runs=q6_module_runs,
            learning_kind="safety_redline",
            summary="Q6 安全红线学习记录已登记。",
            payload=q6_payload,
        )
        q6_execution_diagnosis["module_runs"] = q6_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "forbidden_zone_profile",
                    **profile.model_dump(mode="json"),
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q6_forbidden_zone_profile": profile.model_dump(mode="json"),
                "q6_global_constraints": normalized_global_constraints,
                "q6_redline_hints": normalized_redline_hints,
                "q6_forbidden_zone_baseline": forbidden_zone_baseline,
                "q6_execution_diagnosis": q6_execution_diagnosis,
            },
            confidence=0.99, # Redlines must have near-absolute confidence
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
