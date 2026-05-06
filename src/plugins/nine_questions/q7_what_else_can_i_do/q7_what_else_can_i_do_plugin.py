from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_ids import NINE_QUESTION_Q7
from zentex.plugins.models import PluginLifecycleStatus
from zentex.common.cognitive_result import CognitiveToolResult
from plugins.nine_questions.q3_role_inference.llm_output_table import (
    load_llm_output_from_table as load_q3_llm_output_from_table,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_output_table import (
    load_llm_output_from_table as load_q5_llm_output_from_table,
)
from plugins.nine_questions.q6_what_should_i_not_do.llm_output_table import (
    load_llm_output_from_table as load_q6_llm_output_from_table,
)
from plugins.nine_questions.q7_what_else_can_i_do.llm_prompt import build_q7_llm_request
from plugins.nine_questions.q7_what_else_can_i_do.internal import (
    derive_red_line_assessment_baseline,
    extract_current_intent_context as extract_q7_current_intent_context,
    extract_identity_kernel as extract_q7_identity_kernel,
    extract_procedural_memory_constraints as extract_q7_procedural_memory_constraints,
)
from plugins.nine_questions.q7_what_else_can_i_do.external import (
    extract_safety_rejection_history as extract_q7_safety_rejection_history,
)
from plugins.nine_questions.q7_what_else_can_i_do.models import Q7InferenceResult
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
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_human_readable_block,
    render_q5_boundary,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)


QUESTION_REF = "我的红线与约束是什么"
_Q7_MAX_LLM_ATTEMPTS = 3


def _coerce_text_list(value: Any, *, limit: int = 20) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    elif value in (None, "", {}, []):
        raw_items = []
    else:
        raw_items = [value]
    normalized: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            text = "；".join(
                f"{key}: {val}"
                for key, val in item.items()
                if val not in (None, "", [], {})
            )
        else:
            text = str(item or "")
        text = text.strip()
        if text:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return list(dict.fromkeys(normalized))


def _extract_identity_kernel(context: dict[str, Any], upstream_context: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "identity_kernel_snapshot",
        "identity_kernel",
        "q3_identity_kernel_snapshot",
        "q3_identity_kernel",
        "q2_identity_kernel_snapshot",
        "q2_identity_kernel",
    ):
        identity = upstream_context.get(key)
        if isinstance(identity, dict) and identity:
            return identity
    q3_role_profile = upstream_context.get("q3_role_profile")
    if isinstance(q3_role_profile, dict):
        identity = q3_role_profile.get("identity_kernel_snapshot") or q3_role_profile.get("identity_kernel")
        if isinstance(identity, dict) and identity:
            return identity
    state_identity = context.get("identity_kernel_snapshot") or context.get("identity_kernel")
    if isinstance(state_identity, dict) and state_identity:
        return state_identity
    store = context.get("system_identity_store")
    get_identity = getattr(store, "get_identity", None)
    if callable(get_identity):
        payload = get_identity()
        if isinstance(payload, dict):
            snapshot = payload.get("identity_kernel_snapshot")
            if isinstance(snapshot, dict) and snapshot:
                return snapshot
            return payload
    return {}


def _extract_safety_rejection_history(context: dict[str, Any], upstream_context: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    for key in (
        "rejected_operation_records",
        "safety_rejection_history",
        "safety_gate_rejections",
        "safety_gate_audit_log",
        "cloud_audit_rejections",
        "cloud_audit_decisions",
        "g12_safety_gate_history",
        "g30_cloud_audit_history",
    ):
        candidates.extend(_coerce_text_list(context.get(key), limit=30))
        candidates.extend(_coerce_text_list(upstream_context.get(key), limit=30))
    return list(dict.fromkeys(item for item in candidates if item))[:30]


def _extract_current_intent_context(context: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "current_intent_context",
        "current_user_intent",
        "user_intent",
        "objective",
        "current_objective",
        "task_request",
        "question_text",
        "current_goal",
    )
    intent: dict[str, Any] = {}
    for key in keys:
        value = context.get(key)
        if value not in (None, "", [], {}):
            intent[key] = value
    parameters = context.get("parameters")
    if isinstance(parameters, dict):
        for key in ("question_text", "current_intent_context", "user_intent", "task_request"):
            value = parameters.get(key)
            if value not in (None, "", [], {}):
                intent[f"parameters.{key}"] = value
    return intent


def _extract_procedural_memory_constraints(context: dict[str, Any]) -> list[str]:
    constraints = _coerce_text_list(
        context.get("procedural_memory_constraints") or context.get("g38_procedural_constraints"),
        limit=20,
    )
    memory_service = context.get("memory_service")
    list_procedural_records = getattr(memory_service, "list_procedural_records", None)
    if callable(list_procedural_records):
        try:
            for record in list_procedural_records()[:40]:
                tags = [str(item).lower() for item in (getattr(record, "tags", []) or [])]
                text = str(
                    getattr(record, "summary", "")
                    or getattr(record, "content", "")
                    or getattr(record, "title", "")
                    or ""
                ).strip()
                payload = getattr(record, "payload", {}) or {}
                payload_text = " ".join(str(value) for value in payload.values() if value not in (None, "", [], {}))
                combined = f"{text} {payload_text}".lower()
                if any(token in combined for token in ("constraint", "redline", "red line", "禁止", "红线", "不可绕过")) or "procedural" in tags:
                    constraints.append(text or payload_text)
                if len(constraints) >= 20:
                    break
        except Exception:
            logger.exception("Q7 procedural memory constraint extraction failed")
    return list(dict.fromkeys(item for item in constraints if str(item).strip()))[:20]


def _build_q7_trace_payload(
    *,
    request_id: str,
    decision_id: str,
    provider_name: str,
    model_name: Any,
    system_prompt: str,
    prompt: str,
    caller_context: Any,
    model_context: dict[str, Any],
    raw_response: dict[str, Any],
    result: dict[str, Any],
    token_usage: dict[str, Any],
    elapsed_ms: int,
    invocations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "decision_id": decision_id,
        "provider_name": provider_name,
        "model": model_name,
        "system_prompt": system_prompt,
        "prompt": prompt,
        "source_module": caller_context.source_module,
        "invocation_phase": caller_context.invocation_phase,
        "question_driver_refs": caller_context.question_driver_refs,
        "context_data": model_context,
        "result": result,
        "raw_response": raw_response,
        "token_usage": {
            "input_tokens": int(token_usage.get("input_tokens") or 0),
            "output_tokens": int(token_usage.get("output_tokens") or 0),
            "total_tokens": int(token_usage.get("total_tokens") or 0),
        },
        "elapsed_ms": elapsed_ms,
        "invocations": invocations,
    }


class WhatElseCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q7
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q7"
    display_name: str = "Q7: What are my red lines and constraints?"
    description: str = "Assess non-bypassable red lines and active constraints before Q8 tasking."
    behavior_key: str = "q7_red_line_assessment"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["unhandled_q7_failure"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q7_module_runs = bind_module_runs(context, "q7")
        upstream_context = {
            **load_q3_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
            **load_q5_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
            **load_q6_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
        }

        identity_kernel = extract_q7_identity_kernel(context, upstream_context)
        q3_mission_boundary = upstream_context.get("q3_mission_boundary") or {}
        q5_profile = upstream_context.get("q5_authorization_boundary_profile") or {}
        q5_permission_boundary = upstream_context.get("q5_permission_boundary") or {}
        q6_profile = (
            upstream_context.get("q6_consequence_inference")
            or upstream_context.get("q6_cost_impact_profile")
            or upstream_context.get("q6_consequence_assessment")
            or upstream_context.get("q6_forbidden_zone_profile")
            or {}
        )
        safety_rejection_history = extract_q7_safety_rejection_history(context, upstream_context)
        procedural_memory_constraints = extract_q7_procedural_memory_constraints(context)
        current_intent_context = extract_q7_current_intent_context(context)
        if not identity_kernel:
            raise RuntimeError("q7_identity_kernel_missing")
        if not isinstance(q3_mission_boundary, dict) or not q3_mission_boundary:
            raise RuntimeError("q7_q3_mission_boundary_missing")
        if not q5_profile and not q5_permission_boundary:
            raise RuntimeError("q7_q5_authorization_boundary_missing")

        dependency_validation_run = start_module_run(
            q7_module_runs,
            "q7_dependency_validation",
            source="plugins.nine_questions.q7",
        )
        finish_module_run(dependency_validation_run)

        red_line_baseline = derive_red_line_assessment_baseline(
            identity_kernel=identity_kernel if isinstance(identity_kernel, dict) else {},
            q3_mission_boundary=q3_mission_boundary if isinstance(q3_mission_boundary, dict) else {},
            q5_profile=q5_profile if isinstance(q5_profile, dict) else {},
            q5_permission_boundary=q5_permission_boundary if isinstance(q5_permission_boundary, dict) else {},
            q6_profile=q6_profile if isinstance(q6_profile, dict) else {},
            safety_rejection_history=safety_rejection_history,
            procedural_memory_constraints=procedural_memory_constraints,
        )
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_dependency_validation",
            payload={
                "identity_kernel_snapshot": identity_kernel,
                "q3_mission_boundary": q3_mission_boundary,
                "q5_authorization_boundary_profile": q5_profile,
                "q5_permission_boundary": q5_permission_boundary,
                "q6_consequence_profile": q6_profile,
                "safety_rejection_history": safety_rejection_history,
                "procedural_memory_constraints": procedural_memory_constraints,
                "q7_red_line_baseline": red_line_baseline,
            },
            status=str(dependency_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )

        red_line_baseline_run = start_module_run(
            q7_module_runs,
            "q7_red_line_baseline_projection",
            source="plugins.nine_questions.q7",
        )
        finish_module_run(red_line_baseline_run, status="completed")
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_red_line_baseline_projection",
            payload=red_line_baseline,
            status=str(red_line_baseline_run.get("status") or "completed"),
            output_kind="evidence",
        )

        llm_request = build_q7_llm_request(
            rendered_q3_mission_boundaries=render_human_readable_block(q3_mission_boundary, heading="Q3 使命与连续性边界（Q3_Mission_Boundaries）"),
            rendered_identity_kernel=render_human_readable_block(identity_kernel, heading="身份边界底线（Identity_Boundary）"),
            rendered_q5_boundary=render_q5_boundary(upstream_context),
            rendered_safety_rejections=render_human_readable_block(safety_rejection_history or ["未发现近期正式拒绝记录"], heading="近期安全与审计拦截历史（Safety_Audit_Records）"),
            rendered_current_intent_context=render_human_readable_block(current_intent_context or {"status": "未发现显式当前意图上下文"}, heading="当前意图上下文（Current_Intent_Context）"),
            rendered_red_line_baseline=render_human_readable_block(red_line_baseline, heading="Q7 红线预处理基线"),
            q3_mission_boundaries=q3_mission_boundary if isinstance(q3_mission_boundary, dict) else {},
            identity_kernel=identity_kernel if isinstance(identity_kernel, dict) else {},
            q5_authorization_boundary={
                "q5_authorization_boundary_profile": q5_profile,
                "q5_permission_boundary": q5_permission_boundary,
            },
            safety_rejection_history=safety_rejection_history,
            current_intent_context=current_intent_context,
            red_line_baseline=red_line_baseline,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]

        trace_id = str(context.get("trace_id") or f"q7-redline:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q7_red_line_assessment")

        caller_context = build_caller_context(
            source_module="q7_what_else_can_i_do_plugin",
            invocation_phase="nine_question_q7_red_line_assessment",
            question_ref=QUESTION_REF,
            decision_id=decision_id,
            trace_id=trace_id,
        )

        model_context = llm_request["model_context"]
        red_line_projection_run = start_module_run(
            q7_module_runs,
            "q7_red_line_assessment_projection",
            source="plugins.nine_questions.q7",
        )

        inference: Q7InferenceResult | None = None
        raw: dict[str, Any] = {}
        validation_errors: list[str] = []
        invocation_traces: list[dict[str, Any]] = []
        elapsed_ms = 0
        for attempt in range(1, _Q7_MAX_LLM_ATTEMPTS + 1):
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
                    "attempt": attempt,
                    "system_prompt": system_prompt,
                    "prompt": prompt,
                    "context": model_context,
                },
            )
            try:
                started = perf_counter()
                raw = provider.generate_json(
                    prompt=f"{system_prompt}\n\n{prompt}",
                    context=model_context,
                    caller_context=caller_context,
                )
                elapsed_ms += int((perf_counter() - started) * 1000)
                inference = Q7InferenceResult.model_validate(raw)
                raw_response_payload = json_safe_payload(getattr(provider, "last_raw_response", None))
                if not isinstance(raw_response_payload, dict):
                    raw_response_payload = json_safe_payload(raw) if isinstance(raw, dict) else {}
                token_usage_payload = json_safe_payload(getattr(provider, "last_token_usage", None))
                token_usage_payload = token_usage_payload if isinstance(token_usage_payload, dict) else {}
                invocation_traces.append(
                    {
                        "attempt": attempt,
                        "status": "validated",
                        "raw_response": raw_response_payload,
                        "token_usage": token_usage_payload,
                    }
                )
                break
            except Exception as exc:
                validation_errors.append(f"attempt_{attempt}:{exc.__class__.__name__}:{exc}")
                raw_response_payload = json_safe_payload(getattr(provider, "last_raw_response", None))
                if not isinstance(raw_response_payload, dict):
                    raw_response_payload = json_safe_payload(raw) if isinstance(raw, dict) else {}
                invocation_traces.append(
                    {
                        "attempt": attempt,
                        "status": "invalid",
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                        "raw_response": raw_response_payload,
                    }
                )
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
                        "caller_context": caller_context.model_dump(mode="json"),
                        "attempt": attempt,
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    },
                )
                if attempt >= _Q7_MAX_LLM_ATTEMPTS:
                    logger.exception("Q7 RedLineAssessment validation failed after retries")

        if inference is None:
            fail_module_run(
                red_line_projection_run,
                error_code="q7_red_line_assessment_validation_failed",
                error_message="; ".join(validation_errors),
            )
            raise RuntimeError("q7_red_line_assessment_validation_failed")

        assessment = inference.RedLineAssessment
        assessment_payload = assessment.model_dump(mode="json")
        deterministic_constraints = red_line_baseline.get("non_bypassable_constraints", [])
        if deterministic_constraints:
            merged_constraints = list(
                dict.fromkeys(
                    _coerce_text_list(assessment_payload.get("non_bypassable_constraints"), limit=100)
                    + _coerce_text_list(deterministic_constraints, limit=100)
                )
            )
            assessment_payload["non_bypassable_constraints"] = merged_constraints
        deterministic_rejections = red_line_baseline.get("safety_rejection_history", [])
        if deterministic_rejections:
            assessment_payload["rejected_operations_log"] = list(
                dict.fromkeys(
                    _coerce_text_list(assessment_payload.get("rejected_operations_log"), limit=100)
                    + _coerce_text_list(deterministic_rejections, limit=100)
                )
            )
        if not assessment_payload.get("constraint_sources_explanation"):
            assessment_payload["constraint_sources_explanation"] = (
                "当前禁令源于身份边界的底层不可绕过约束、Q5 授权黑名单与安全拦截记录。"
            )
        compatibility_payload = {
            "current_red_line_hits": assessment_payload["current_redline_hits"],
            "rejected_operation_records": assessment_payload["rejected_operations_log"],
            "ban_source_explanations": [assessment_payload["constraint_sources_explanation"]],
            "non_bypassable_constraints": assessment_payload["non_bypassable_constraints"],
            "question_driver_refs": red_line_baseline.get("question_driver_refs") or [
                "Identity_Boundary",
                "Q5_Authorization",
                "Safety_Audit_Records",
                "Current_Intent_Context",
            ],
        }
        root_assessment_payload = {"RedLineAssessment": assessment_payload}

        finish_module_run(red_line_projection_run, status="completed")
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_red_line_assessment_projection",
            payload=root_assessment_payload,
            status=str(red_line_projection_run.get("status") or "completed"),
            output_kind="inference",
        )

        raw_response_payload = json_safe_payload(getattr(provider, "last_raw_response", None))
        if not isinstance(raw_response_payload, dict):
            raw_response_payload = json_safe_payload(raw) if isinstance(raw, dict) else {}
        token_usage_payload = json_safe_payload(getattr(provider, "last_token_usage", None))
        token_usage_payload = token_usage_payload if isinstance(token_usage_payload, dict) else {}
        model_name = json_safe_payload(
            getattr(provider, "last_model_name", None)
            or context.get("llm_model")
            or context.get("model")
            or context.get("model_name")
        )
        provider_name = safe_provider_plugin_id(provider) or str(context.get("model_provider") or "").strip()
        llm_trace_payload = _build_q7_trace_payload(
            request_id=request_id,
            decision_id=decision_id,
            provider_name=provider_name,
            model_name=model_name,
            system_prompt=system_prompt,
            prompt=prompt,
            caller_context=caller_context,
            model_context=model_context,
            raw_response=raw_response_payload,
            result=root_assessment_payload,
            token_usage=token_usage_payload,
            elapsed_ms=elapsed_ms,
            invocations=invocation_traces,
        )

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
                "caller_context": caller_context.model_dump(mode="json"),
                "result": root_assessment_payload,
                "raw_response": raw_response_payload,
                "token_usage": token_usage_payload,
                "model": model_name,
                "elapsed_ms": elapsed_ms,
                "llm_trace_payload": llm_trace_payload,
            },
        )

        summary = (
            f"red_line_hits={len(assessment_payload['current_redline_hits'])}; "
            f"rejections={len(assessment_payload['rejected_operations_log'])}; "
            f"non_bypassable={len(assessment_payload['non_bypassable_constraints'])}"
        )
        q7_execution_diagnosis = {
            "authenticity_status": "completed",
            "diagnosis_code": "red_line_assessment_completed",
            "diagnosis_message": "Q7 completed with validated RedLineAssessment.",
            "module_runs": list(q7_module_runs),
            "plugin_runs": [],
            "upstream_dependencies": [
                {
                    "dependency_id": "q2_identity_kernel",
                    "required": True,
                    "status": "completed" if identity_kernel else "missing",
                    "message": "Identity boundary provides bottom non-bypassable constraints.",
                },
                {
                    "dependency_id": "q5",
                    "required": True,
                    "status": "completed" if q5_profile or q5_permission_boundary else "missing",
                    "message": "Q5 authorization boundary constrains Q7 red lines.",
                },
                {
                    "dependency_id": "g12_g30",
                    "required": False,
                    "status": "completed" if safety_rejection_history else "empty",
                    "message": "Safety gate and audit rejected-operation history.",
                },
                {
                    "dependency_id": "g38",
                    "required": False,
                    "status": "completed" if procedural_memory_constraints else "empty",
                    "message": "Procedural memory active constraints.",
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
                        reason="重新执行红线与约束评估。",
                        path="/api/web/nine-questions/q7/run",
                    ),
                    build_recovery_action(
                        "q7-refresh-redline-baseline",
                        label="刷新 Q7 红线证据",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q7_red_line_baseline_projection",
                        reason="重新读取身份边界、Q5、安全拦截历史和程序记忆。",
                        path="/api/web/nine-questions/q7/modules/q7_red_line_baseline_projection/retry",
                    ),
                ],
            ),
            "projection_summary": {
                "current_redline_hits": assessment_payload["current_redline_hits"],
                "rejected_operations_log": assessment_payload["rejected_operations_log"],
                "non_bypassable_constraints": assessment_payload["non_bypassable_constraints"],
            }
        }
        q7_module_runs = q7_execution_diagnosis.get("module_runs")
        q7_module_runs = q7_module_runs if isinstance(q7_module_runs, list) else []
        q7_payload = assessment_payload
        run_audit_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            summary="Q7 红线与约束评估审计已记录。",
            payload={
                "q7_red_line_assessment": root_assessment_payload,
                "q7_red_line_assessment_compat": compatibility_payload,
                "q7_red_line_baseline": red_line_baseline,
                "llm_trace_payload": llm_trace_payload,
            },
        )
        run_memory_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            title="Q7 Red Line Assessment",
            summary="Q7 红线与不可绕过约束已写入记忆。",
            layer="episodic",
            payload=root_assessment_payload,
            tags=["nine-questions", "q7", "red-line-assessment"],
        )
        run_reflection_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            subject="Q7 red-line firewall",
            summary="Q7 红线防火墙有效性反思已记录。",
            reflection_type="strategy_reflection",
            payload={"q7_red_line_assessment": root_assessment_payload},
        )
        run_learning_integration(
            context,
            question_id="q7",
            module_runs=q7_module_runs,
            learning_kind="red_line_assessment",
            summary="Q7 红线约束学习记录已登记。",
            payload=root_assessment_payload,
        )
        q7_execution_diagnosis["module_runs"] = q7_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[{"kind": "red_line_assessment", **root_assessment_payload}],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "RedLineAssessment": assessment_payload,
                "red_line_assessment": root_assessment_payload,
                "q7_red_line_assessment": root_assessment_payload,
                "q7_red_line_assessment_compat": compatibility_payload,
                "q7_red_line_baseline": red_line_baseline,
                "q7_current_redline_hits": assessment_payload["current_redline_hits"],
                "q7_current_red_line_hits": compatibility_payload["current_red_line_hits"],
                "q7_rejected_operations_log": assessment_payload["rejected_operations_log"],
                "q7_rejected_operation_records": compatibility_payload["rejected_operation_records"],
                "q7_constraint_sources_explanation": assessment_payload["constraint_sources_explanation"],
                "q7_ban_source_explanations": compatibility_payload["ban_source_explanations"],
                "q7_non_bypassable_constraints": assessment_payload["non_bypassable_constraints"],
                "q7_question_driver_refs": compatibility_payload["question_driver_refs"],
                "q7_absolute_red_lines": assessment_payload["non_bypassable_constraints"],
                "q7_execution_diagnosis": q7_execution_diagnosis,
                "llm_trace_payload": llm_trace_payload,
            },
            llm_trace_payload=llm_trace_payload,
            confidence=0.7,
        )


def build_q7_what_else_can_i_do_plugin() -> WhatElseCanIDoPlugin:
    return WhatElseCanIDoPlugin()
