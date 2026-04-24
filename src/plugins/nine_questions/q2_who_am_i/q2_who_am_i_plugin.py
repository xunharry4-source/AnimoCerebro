from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q2
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q2_who_am_i.models import Q2WhoAmIInference
from plugins.nine_questions.q2_who_am_i.llm_prompt import build_q2_llm_request
from plugins.nine_questions.q2_who_am_i.modules import (
    Q2IdentityInputError,
    build_q2_identity_input_context,
    json_compatible,
    normalize_q2_inference_payload,
    safe_provider_plugin_id,
    serialize_constraint_payload,
    serialize_role_payload,
)
# Decoupled: Inputs come from identity and weight plugins
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


QUESTION_REF = "我是谁"


from zentex.common.nine_questions_shared import (
    build_nine_question_partial_failure,
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
    build_model_context,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
)

logger = logging.getLogger(__name__)


def _coerce_risk_weight(
    raw_value: object,
    *,
    fallback: float,
    log_message: str,
    extra: dict[str, Any],
) -> float:
    try:
        return max(0.0, min(1.0, float(raw_value)))
    except Exception:
        # 严禁吞掉风险权重脏输入并假装 Q2 正常。
        # 这里允许回落到稳定默认值继续推理，但必须保留异常堆栈；否则真实输入污染会被伪装成正常运行。
        logger.exception(log_message, extra=extra)
        return max(0.0, min(1.0, fallback))


def _build_q2_fallback_inference_payload(
    *,
    workspace_domain_inference: dict[str, Any],
    identity_kernel: dict[str, Any],
    role_payload: dict[str, Any],
    constraint_payload: dict[str, Any],
) -> dict[str, Any]:
    identity_role = str(
        role_payload.get("identity_role")
        or identity_kernel.get("identity_role")
        or workspace_domain_inference.get("primary_domain")
        or "runtime_operator"
    ).strip() or "runtime_operator"
    active_role = str(
        role_payload.get("active_role_default")
        or role_payload.get("active_role")
        or identity_role
    ).strip() or identity_role
    task_role = str(
        role_payload.get("task_role")
        or role_payload.get("execution_role")
        or active_role
    ).strip() or active_role
    mission_text = str(
        role_payload.get("mission")
        or identity_kernel.get("mission")
        or workspace_domain_inference.get("suggested_first_step")
        or workspace_domain_inference.get("reasoning_summary")
        or "Maintain stable and auditable execution."
    ).strip() or "Maintain stable and auditable execution."

    constraints = constraint_payload.get("non_bypassable_constraints")
    continuity_boundaries = [
        str(item).strip()
        for item in (constraints if isinstance(constraints, list) else [])
        if str(item).strip()
    ]
    if not continuity_boundaries:
        continuity_boundaries = ["preserve_auditability", "respect_operational_constraints"]

    priority_duties: list[str] = []
    mapping = role_payload.get("task_role_mapping")
    if isinstance(mapping, dict):
        priority_duties = [str(key).strip() for key in mapping.keys() if str(key).strip()]
    if not priority_duties:
        core_values = role_payload.get("core_values")
        if isinstance(core_values, list):
            priority_duties = [str(item).strip() for item in core_values if str(item).strip()]
    if not priority_duties:
        priority_duties = ["validate_context", "maintain_service_health"]

    return {
        "role_profile": {
            "identity_role": identity_role,
            "active_role": active_role,
            "task_role": task_role,
        },
        "mission_boundary": {
            "current_mission": mission_text,
            "priority_duties": priority_duties,
            "continuity_boundaries": continuity_boundaries,
        },
    }

class Q2WhoAmIPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q2
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q2"
    display_name: str = "Q2: Who am I?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q2: 我是谁 (dynamic role inference & continuity boundary)

    Enforced red lines:
    - Must use Live LLM (fail-closed; no rule fallback).
    - Must only consume structured summaries from main context snapshot.
    - Must inject provenance via caller_context (source_module + question_driver_refs).
    - Must append-only write prompt/context/response into BrainTranscriptStore.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        plugin_service = context.get("plugin_service")
        try:
            identity_context = build_q2_identity_input_context(
                dict(context),
                plugin_id=self.plugin_id,
                plugin_service=plugin_service,
                functional_executor=execute_enabled_cognitive_plugin_functionals,
                trace_id=str(context.get("trace_id") or "q2"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
        except Q2IdentityInputError as exc:
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q2",
                question_ref=QUESTION_REF,
                error_code="q2_functional_identity_chain_failed",
                error_message=str(exc),
                diagnosis_key="q2_execution_diagnosis",
                module_runs=exc.module_runs,
                plugin_runs=[],
                upstream_dependencies=[
                    {
                        "dependency_id": "q1",
                        "required": True,
                        "status": "completed" if exc.context_updates.get("workspace_domain_inference") else "missing",
                    }
                ],
                context_updates=exc.context_updates,
                required_modules=["q2_functional_identity_chain"],
            )

        workspace_domain_inference = identity_context["workspace_domain_inference"]
        q1_scene_model = identity_context["q1_scene_model"]
        q1_uncertainty_profile = identity_context["q1_uncertainty_profile"]
        identity_kernel = identity_context["identity_kernel"]
        role_payload = identity_context["role_payload"]
        constraint_payload = identity_context["constraint_payload"]
        risk_weight = identity_context["risk_weight"]
        functional_inputs = identity_context["functional_inputs"]
        normalized_role_payload = identity_context["normalized_role_payload"]
        normalized_constraint_payload = identity_context["normalized_constraint_payload"]
        normalized_manual_overrides = identity_context["normalized_manual_overrides"]
        q2_identity_audit = identity_context["q2_identity_audit"]
        q2_module_runs = bind_module_runs(
            context,
            "q2",
            initial=identity_context["module_runs"],
        )

        llm_request = build_q2_llm_request(
            risk_weight=risk_weight,
            role_payload_text=serialize_role_payload(role_payload),
            constraint_payload_text=serialize_constraint_payload(constraint_payload),
            workspace_domain_inference=workspace_domain_inference,
            q1_scene_model=q1_scene_model,
            q1_uncertainty_profile=q1_uncertainty_profile,
            identity_kernel_snapshot=identity_kernel,
            role_payload=normalized_role_payload,
            constraint_payload=normalized_constraint_payload,
            functional_identity_inputs=(functional_inputs if plugin_service is not None else []),
            manual_role_overrides=normalized_manual_overrides,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        trace_id = str(context.get("trace_id") or f"q2-who-am-i:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q2_who_am_i")

        caller_context = build_caller_context(
            source_module="q2_who_am_i_plugin",
            invocation_phase="nine_question_q2_who_am_i",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q2_who_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        role_reasoning_run = start_module_run(
            q2_module_runs,
            "q2_role_reasoning_projection",
            source="plugins.nine_questions.q2",
        )

        started = perf_counter()
        llm_fallback_used = False
        llm_fallback_reason = ""
        try:
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            # 严禁吞掉 Q2 LLM 调用异常并仅返回 partial_failed 而没有异常日志。
            # 这里必须保留堆栈，否则后台推理故障会被误判成普通缺数据。
            logger.exception("Q2 LLM invocation failed")
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q2_who_am_i",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            llm_fallback_used = True
            llm_fallback_reason = str(exc)
            raw = _build_q2_fallback_inference_payload(
                workspace_domain_inference=workspace_domain_inference,
                identity_kernel=identity_kernel,
                role_payload=normalized_role_payload,
                constraint_payload=normalized_constraint_payload,
            )

        try:
            normalized_raw = normalize_q2_inference_payload(raw)
            inference = Q2WhoAmIInference.model_validate(normalized_raw)

            # Manual override has highest priority.
            manual_role_overrides = normalized_manual_overrides
            override_active_role = manual_role_overrides.get("active_role_override")
            applied_override = False
            if isinstance(override_active_role, str) and override_active_role.strip():
                role_profile = inference.role_profile.model_copy(
                    update={"active_role": override_active_role.strip()}
                )
                inference = inference.model_copy(update={"role_profile": role_profile})
                applied_override = True
        except Exception as exc:
            # 严禁吞掉 Q2 输出校验/后处理异常并伪装成普通失败结果。
            # 这里必须记录异常日志，否则系统稳定性问题会被隐藏。
            logger.exception("Q2 output validation failed")
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q2_who_am_i",
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
                role_reasoning_run,
                error_code="q2_output_validation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q2",
                question_ref=QUESTION_REF,
                error_code="q2_output_validation_failed",
                error_message=str(exc),
                diagnosis_key="q2_execution_diagnosis",
                module_runs=list(q2_module_runs),
                plugin_runs=[],
                upstream_dependencies=[{"dependency_id": "q1", "required": True, "status": "completed" if workspace_domain_inference else "missing"}],
                context_updates={
                    "workspace_domain_inference": workspace_domain_inference,
                    "q1_scene_model": q1_scene_model,
                    "q1_uncertainty_profile": q1_uncertainty_profile,
                    "identity_kernel_snapshot": identity_kernel,
                    "manual_role_overrides": normalized_manual_overrides,
                    "q2_role_payload": normalized_role_payload,
                    "q2_constraint_payload": normalized_constraint_payload,
                },
                required_modules=[
                    "q2_q1_dependency_validation",
                    "q2_identity_kernel_validation",
                    "q2_role_reasoning_projection",
                ],
            )

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q2_who_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "normalized_response_applied": normalized_raw != raw,
                "manual_override_applied": applied_override,
                "raw_response": json_compatible(getattr(provider, "last_raw_response", None)),
                "token_usage": json_compatible(getattr(provider, "last_token_usage", {})) or {},
                "model": (
                    str(getattr(provider, "last_model_name", "") or getattr(provider, "default_model", "")).strip()
                    or None
                ),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )

        role_summary = (
            f"identity_role={inference.role_profile.identity_role}; "
            f"active_role={inference.role_profile.active_role}; "
            f"task_role={inference.role_profile.task_role}"
        )
        finish_module_run(
            role_reasoning_run,
            status="degraded" if not workspace_domain_inference or not identity_kernel else "completed",
            error_code="" if workspace_domain_inference and identity_kernel else "upstream_degraded",
            error_message="" if workspace_domain_inference and identity_kernel else "Role reasoning used degraded inputs.",
            used_fallback=llm_fallback_used or (not workspace_domain_inference or not identity_kernel),
        )
        q2_execution_diagnosis = {
            "authenticity_status": "degraded" if not workspace_domain_inference or not identity_kernel else "completed",
            "diagnosis_code": "identity_context_degraded" if not workspace_domain_inference or not identity_kernel else "completed",
            "diagnosis_message": (
                "Q2 used degraded upstream identity context."
                if not workspace_domain_inference or not identity_kernel
                else "Q2 role reasoning completed with validated context."
            ),
            "used_fallback": llm_fallback_used or not workspace_domain_inference or not identity_kernel or plugin_service is None,
            "llm_fallback_used": llm_fallback_used,
            "llm_fallback_reason": llm_fallback_reason,
            "upstream_degraded": not workspace_domain_inference,
            "module_runs": list(q2_module_runs),
            "plugin_runs": [],
            "upstream_dependencies": [
                {
                    "dependency_id": "q1",
                    "required": True,
                    "status": "completed" if workspace_domain_inference else "missing",
                    "message": "Q1 workspace domain inference required.",
                }
            ],
            "recovery_plan": build_recovery_plan(
                question_id="q2",
                retriable=True,
                rollback_available=True,
                partial_retry_available=True,
                partial_replace_available=False,
                actions=[
                    build_recovery_action(
                        "q2-rerun-question",
                        label="重跑 Q2 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q2",
                        reason="重新执行 Q2 角色推理链。",
                        path="/api/web/nine-questions/q2/run",
                    ),
                    build_recovery_action(
                        "q2-refresh-identity-inputs",
                        label="刷新 Q2 身份输入链",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q2_functional_identity_chain",
                        reason="仅刷新 Q2 的 Q1 依赖、identity kernel、functional identity inputs；不伪装重跑 LLM 角色推理。",
                        path="/api/web/nine-questions/q2/modules/q2_functional_identity_chain/retry",
                    ),
                    build_recovery_action(
                        "q2-rerun-upstream-q1",
                        label="先重跑 Q1 再重跑 Q2",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q1->q2",
                        reason="Q2 依赖 Q1 环境态势，Q1 失真时先修复上游。",
                        path="/api/web/nine-questions/q1/run",
                    ),
                    build_recovery_action(
                        "q2-rollback-previous-success",
                        label="沿用上一份 committed success",
                        kind="rollback",
                        executable=True,
                        scope="record",
                        target="q2",
                        reason="当前持久化层已支持失败时沿用上一份 Q2 成功角色推断结果。",
                        path="/api/web/nine-questions/q2/rollback",
                    ),
                ],
            ),
        }
        persist_question_module_output(
            context,
            question_id="q2",
            module_id="q2_role_reasoning_projection",
            payload={
                "role_profile": inference.role_profile.model_dump(mode="json"),
                "mission_boundary": inference.mission_boundary.model_dump(mode="json"),
                "risk_preference": {
                    "base_weight": risk_weight,
                    "posture_label": "conservative" if risk_weight > 0.6 else "aggressive" if risk_weight < 0.4 else "balanced",
                    "reasoning": f"Derived from Q1 uncertainty intensity ({risk_weight:.2f}).",
                    "impact_on_decision": "Preference applied to role inference boundaries.",
                },
            },
            status=str(role_reasoning_run.get("status") or "completed"),
            output_kind="inference",
        )
        q2_module_runs = q2_execution_diagnosis.get("module_runs")
        q2_module_runs = q2_module_runs if isinstance(q2_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q2",
            module_runs=q2_module_runs,
            summary="Q2 身份推断审计已记录。",
            payload={
                "q2_role_profile": inference.role_profile.model_dump(mode="json"),
                "q2_mission_boundary": inference.mission_boundary.model_dump(mode="json"),
                "q2_identity_audit": q2_identity_audit,
            },
        )
        run_memory_integration(
            context,
            question_id="q2",
            module_runs=q2_module_runs,
            title="Q2 Role Profile",
            summary="Q2 角色与使命边界已写入记忆。",
            layer="episodic",
            payload={
                "q2_role_profile": inference.role_profile.model_dump(mode="json"),
                "q2_mission_boundary": inference.mission_boundary.model_dump(mode="json"),
            },
            tags=["nine-questions", "q2", "identity"],
        )
        run_reflection_integration(
            context,
            question_id="q2",
            module_runs=q2_module_runs,
            subject="Q2 identity boundary",
            summary="Q2 身份漂移与边界反思已记录。",
            reflection_type="strategy_reflection",
            payload={
                "q2_role_profile": inference.role_profile.model_dump(mode="json"),
                "q2_mission_boundary": inference.mission_boundary.model_dump(mode="json"),
                "q2_identity_audit": q2_identity_audit,
            },
        )
        run_learning_integration(
            context,
            question_id="q2",
            module_runs=q2_module_runs,
            learning_kind="identity_boundary",
            summary="Q2 身份边界学习记录已登记。",
            payload={
                "q2_role_profile": inference.role_profile.model_dump(mode="json"),
                "q2_mission_boundary": inference.mission_boundary.model_dump(mode="json"),
            },
        )
        q2_execution_diagnosis["module_runs"] = q2_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=role_summary,
            proposals=[
                {
                    "kind": "role_profile",
                    "question_ref": QUESTION_REF,
                    **inference.role_profile.model_dump(mode="json"),
                },
                {
                    "kind": "mission_continuity_boundary",
                    **inference.mission_boundary.model_dump(mode="json"),
                },
            ],
            risks=[
                {
                    "kind": "continuity_boundaries",
                    "items": inference.mission_boundary.continuity_boundaries,
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: inference.role_profile.active_role},
                "workspace_domain_inference": workspace_domain_inference,
                "q1_scene_model": q1_scene_model,
                "q1_uncertainty_profile": q1_uncertainty_profile,
                "identity_kernel_snapshot": identity_kernel,
                "manual_role_overrides": normalized_manual_overrides,
                "q2_role_payload": normalized_role_payload,
                "q2_constraint_payload": normalized_constraint_payload,
                "q2_risk_weight": risk_weight,
                "q2_risk_preference": {
                    "base_weight": risk_weight,
                    "posture_label": "conservative" if risk_weight > 0.6 else "aggressive" if risk_weight < 0.4 else "balanced",
                    "reasoning": f"Derived from Q1 uncertainty intensity ({risk_weight:.2f}).",
                    "impact_on_decision": "Preference applied to role inference boundaries."
                },
                "q2_identity_audit": q2_identity_audit,
                "q2_functional_identity_inputs": functional_inputs,
                "q2_role_profile": inference.role_profile.model_dump(mode="json"),
                "q2_mission_boundary": inference.mission_boundary.model_dump(mode="json"),
                "q2_execution_diagnosis": q2_execution_diagnosis,
                "mission_continuity_projection": inference.mission_boundary.model_dump(mode="json"),
                "mission_continuity_projection_meta": {
                    "continuity_count": len(inference.mission_boundary.continuity_boundaries),
                    "is_locked": bool(identity_kernel.get("continuity_lock")),
                }
            },
            confidence=0.75,
        )


def build_q2_who_am_i_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q2,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q2WhoAmIPlugin:
    return Q2WhoAmIPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q2",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
