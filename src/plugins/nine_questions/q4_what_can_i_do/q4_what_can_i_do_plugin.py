from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q4
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q4_what_can_i_do.modules import (
    contains_write_like_action,
    derive_capability_baseline,
    derive_permission_profile,
    merge_with_capability_baseline,
    normalize_functional_capabilities,
)
from plugins.nine_questions.q4_what_can_i_do.models import Q4WhatCanIDoInference
from plugins.nine_questions.q4_what_can_i_do.llm_prompt import build_q4_llm_request


QUESTION_REF = "我能做什么"


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
    render_plugin_catalog,
    render_q3_asset_inventory,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

logger = logging.getLogger(__name__)
class Q4WhatCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q4
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q4"
    display_name: str = "Q4: What can I do?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q4: 我能做什么 (capability boundary profile)

    Anti-hallucination enforcement:
    - LLM must operate strictly within Q3 asset inventory + permissions.
    - Post-validate actionable_space does not claim write actions when the input states read-only / no execution tools.
    - Violations are fail-closed (raise), never silently corrected.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q4_module_runs = bind_module_runs(context, "q4")
        upstream_context = load_authoritative_question_context_from_storage(context, ["q1", "q2", "q3"])
        q3_inventory = upstream_context.get("q3_unified_asset_inventory", {}) or {}
        if not isinstance(q3_inventory, dict):
            q3_inventory = {}
        inventory_validation_run = start_module_run(
            q4_module_runs,
            "q4_inventory_validation",
            source="plugins.nine_questions.q4",
        )
        exec_domains = list(q3_inventory.get("available_execution_tools", []) or [])
        plugin_service = context.get("plugin_service")
        functional_capabilities: list[dict[str, Any]] = []
        execution_capability_run = start_module_run(
            q4_module_runs,
            "q4_execution_capability_verification",
            source="plugins.nine_questions.q4",
        )
        if plugin_service is not None:
            try:
                functional_capabilities = execute_enabled_cognitive_plugin_functionals(
                    plugin_service,
                    self.plugin_id,
                    default_parameters={"context": dict(context)},
                    trace_id=str(context.get("trace_id") or "q4"),
                    originator_id=str(context.get("session_id") or "unknown-session"),
                    caller_plugin_id=self.plugin_id,
                )
            except Exception as exc:
                # 严禁吞掉 Q4 execution capability verification 异常并继续假装系统正常。
                # 如果功能链已经坏了，就必须结构化失败并留下日志，不能把后台故障伪装成“当前没有能力”。
                logger.exception("Q4 functional capability chain failed")
                finish_module_run(
                    inventory_validation_run,
                    status="completed" if q3_inventory else "missing",
                    error_code="" if q3_inventory else "q3_inventory_missing",
                    error_message="" if q3_inventory else "Q3 inventory is missing.",
                )
                fail_module_run(
                    execution_capability_run,
                    error_code="q4_functional_capability_chain_failed",
                    error_message=str(exc),
                )
                return build_nine_question_partial_failure(
                    context=context,
                    tool_id=self.plugin_id,
                    question_id="q4",
                    question_ref=QUESTION_REF,
                    error_code="q4_functional_capability_chain_failed",
                    error_message=str(exc),
                    diagnosis_key="q4_execution_diagnosis",
                    module_runs=list(q4_module_runs),
                    plugin_runs=[],
                    upstream_dependencies=[{"dependency_id": "q3", "required": True, "status": "completed" if q3_inventory else "missing"}],
                    context_updates={"q4_permission_profile": derive_permission_profile(upstream_context, q3_inventory)},
                    required_modules=["q4_execution_capability_verification"],
                )
            exec_domains.extend(
                str(item.get("plugin_id") or "")
                for item in functional_capabilities
                if item.get("status") == "done"
            )
            exec_domains = list(dict.fromkeys(exec_domains))
            finish_module_run(
                execution_capability_run,
                status="degraded" if not exec_domains else "completed",
                error_code="" if exec_domains else "execution_domains_missing",
                error_message="" if exec_domains else "No validated execution domains are available.",
            )
        else:
            finish_module_run(
                execution_capability_run,
                status="missing",
                error_code="plugin_service_missing",
                error_message="Functional capability chain not started.",
            )
        normalized_functional_capabilities = normalize_functional_capabilities(functional_capabilities)
        permission_profile = derive_permission_profile(upstream_context, q3_inventory)
        finish_module_run(
            inventory_validation_run,
            status="degraded" if not q3_inventory else "completed",
            error_code="" if q3_inventory else "q3_inventory_missing",
            error_message="" if q3_inventory else "Q3 inventory is missing.",
        )
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_inventory_validation",
            payload={
                "q1_scene_model": upstream_context.get("q1_scene_model"),
                "q1_uncertainty_profile": upstream_context.get("q1_uncertainty_profile"),
                "q2_role_profile": upstream_context.get("q2_role_profile"),
                "q2_mission_boundary": upstream_context.get("q2_mission_boundary"),
                "q3_unified_asset_inventory": q3_inventory,
                "q3_resource_evaluation": upstream_context.get("q3_resource_evaluation"),
            },
            status=str(inventory_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )
        permission_validation_run = start_module_run(
            q4_module_runs,
            "q4_permission_validation",
            source="plugins.nine_questions.q4",
        )
        finish_module_run(permission_validation_run)
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_permission_validation",
            payload={"q4_permission_profile": permission_profile},
            status=str(permission_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )
        capability_baseline = derive_capability_baseline(
            upstream_context,
            q3_inventory,
            exec_domains,
            permission_profile,
            normalized_functional_capabilities,
        )
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_execution_capability_verification",
            payload={
                "q4_capability_baseline": capability_baseline,
                "q4_active_execution_domains": exec_domains,
            },
            status=str(execution_capability_run.get("status") or "completed"),
            output_kind="evidence",
        )

        execution_domain_catalog = render_plugin_catalog(exec_domains, heading="执行工具目录")
        asset_inventory_summary = render_q3_asset_inventory(upstream_context)
        llm_request = build_q4_llm_request(
            capability_baseline=capability_baseline,
            permission_profile=permission_profile,
            execution_domain_catalog=execution_domain_catalog,
            asset_inventory_summary=asset_inventory_summary,
            snapshot_version=upstream_context.get("snapshot_version"),
            q1_scene_model=upstream_context.get("q1_scene_model"),
            q1_uncertainty_profile=upstream_context.get("q1_uncertainty_profile"),
            q2_role_profile=upstream_context.get("q2_role_profile"),
            q2_mission_boundary=upstream_context.get("q2_mission_boundary"),
            q3_unified_asset_inventory=q3_inventory,
            q3_resource_evaluation=upstream_context.get("q3_resource_evaluation"),
            q3_humanized_asset_inventory=upstream_context.get("q3_humanized_asset_inventory"),
            q3_workspaces_and_permissions=upstream_context.get("workspaces_and_permissions"),
            q3_memory_and_strategy=upstream_context.get("memory_and_strategy"),
            active_execution_domains=exec_domains,
            functional_capabilities=normalized_functional_capabilities,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        trace_id = str(context.get("trace_id") or f"q4-what-can-i-do:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q4_what_can_i_do")

        caller_context = build_caller_context(
            source_module="q4_what_can_i_do_plugin",
            invocation_phase="nine_question_q4_what_can_i_do",
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
            source="plugins.nine_questions.q4_what_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "context": model_context,
            },
        )

        actionability_run = start_module_run(
            q4_module_runs,
            "q4_actionability_projection",
            source="plugins.nine_questions.q4",
        )

        try:
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            # 严禁吞掉 Q4 LLM 调用异常并只返回 partial_failed。
            # 这里必须记录异常堆栈，否则后台能力推理故障会被误判成普通能力不足。
            logger.exception("Q4 LLM invocation failed")
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q4_what_can_i_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                    "snapshot_version": upstream_context.get("snapshot_version"),
                },
            )
            fail_module_run(
                actionability_run,
                error_code="q4_llm_invocation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q4",
                question_ref=QUESTION_REF,
                error_code="q4_llm_invocation_failed",
                error_message=str(exc),
                diagnosis_key="q4_execution_diagnosis",
                module_runs=list(q4_module_runs),
                plugin_runs=[],
                upstream_dependencies=[{"dependency_id": "q3", "required": True, "status": "completed" if q3_inventory else "missing"}],
                context_updates={
                    "q4_permission_profile": permission_profile,
                    "q4_capability_baseline": capability_baseline,
                    "q4_functional_capabilities": normalized_functional_capabilities,
                },
                required_modules=["q4_inventory_validation", "q4_actionability_projection"],
            )

        try:
            inference = Q4WhatCanIDoInference.model_validate(raw)
        except Exception as exc:
            # 严禁吞掉 Q4 输出校验异常并伪装成普通失败结果。
            # 结构化输出异常必须留下日志，否则系统会继续假装功能正常实现。
            logger.exception("Q4 output validation failed")
            fail_module_run(
                actionability_run,
                error_code="q4_output_validation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q4",
                question_ref=QUESTION_REF,
                error_code="q4_output_validation_failed",
                error_message=str(exc),
                diagnosis_key="q4_execution_diagnosis",
                module_runs=list(q4_module_runs),
                plugin_runs=[],
                upstream_dependencies=[{"dependency_id": "q3", "required": True, "status": "completed" if q3_inventory else "missing"}],
                context_updates={
                    "q4_permission_profile": permission_profile,
                    "q4_capability_baseline": capability_baseline,
                    "q4_functional_capabilities": normalized_functional_capabilities,
                },
                required_modules=["q4_inventory_validation", "q4_actionability_projection"],
            )
        profile = inference.capability_boundary_profile
        read_only = bool(permission_profile.get("is_read_only"))
        profile.capability_upper_limits = merge_with_capability_baseline(
            profile.capability_upper_limits,
            capability_baseline.get("capability_upper_limits", []),
            read_only=read_only,
        )
        profile.actionable_space = merge_with_capability_baseline(
            profile.actionable_space,
            capability_baseline.get("actionable_space", []),
            read_only=read_only,
        )
        profile.executable_strategies = merge_with_capability_baseline(
            profile.executable_strategies,
            capability_baseline.get("executable_strategies", []),
            read_only=read_only,
        )

        # Guardrail validation (anti-hallucination): if there is no execution tool or permissions are read-only,
        # the model must not claim write-like actions.
        execution_tools = q3_inventory.get("available_execution_tools") or []
        if not execution_tools:
            read_only = True
        if read_only:
            offending = [a for a in profile.actionable_space if isinstance(a, str) and contains_write_like_action(a)]
            anti_hallucination_run = start_module_run(
                q4_module_runs,
                "q4_anti_hallucination_guard",
                source="plugins.nine_questions.q4",
            )
            if offending:
                finish_module_run(
                    actionability_run,
                    status="degraded" if not exec_domains else "completed",
                    error_code="" if exec_domains else "actionability_degraded",
                    error_message="" if exec_domains else "Actionable space is constrained by missing execution domains.",
                )
                fail_module_run(
                    anti_hallucination_run,
                    error_code="q4_anti_hallucination_violation",
                    error_message="Actionable space contains write-like actions under read-only/no-execution constraints.",
                )
                return build_nine_question_partial_failure(
                    context=context,
                    tool_id=self.plugin_id,
                    question_id="q4",
                    question_ref=QUESTION_REF,
                    error_code="q4_anti_hallucination_violation",
                    error_message="Anti-hallucination violation: actionable_space contains write-like actions while read-only/no execution tools: "
                    + "; ".join(offending[:5]),
                    diagnosis_key="q4_execution_diagnosis",
                    module_runs=list(q4_module_runs),
                    plugin_runs=[],
                    upstream_dependencies=[{"dependency_id": "q3", "required": True, "status": "completed" if q3_inventory else "missing"}],
                    context_updates={
                        "q4_permission_profile": permission_profile,
                        "q4_capability_baseline": capability_baseline,
                        "q4_functional_capabilities": normalized_functional_capabilities,
                    },
                    required_modules=["q4_inventory_validation", "q4_anti_hallucination_guard"],
                )
            finish_module_run(anti_hallucination_run)
        else:
            anti_hallucination_run = start_module_run(
                q4_module_runs,
                "q4_anti_hallucination_guard",
                source="plugins.nine_questions.q4",
            )
            finish_module_run(anti_hallucination_run)

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q4_what_can_i_do",
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

        summary = f"actionable={len(profile.actionable_space)}; strategies={len(profile.executable_strategies)}"
        finish_module_run(
            actionability_run,
            status="degraded" if not exec_domains else "completed",
            error_code="" if exec_domains else "actionability_degraded",
            error_message="" if exec_domains else "Actionable space is constrained by missing execution domains.",
        )
        q4_execution_diagnosis = {
            "authenticity_status": "degraded" if not q3_inventory or not exec_domains else "completed",
            "diagnosis_code": "capability_boundary_degraded" if not q3_inventory or not exec_domains else "completed",
            "diagnosis_message": (
                "Q4 capability boundary completed with degraded asset or execution-domain evidence."
                if not q3_inventory or not exec_domains
                else "Q4 capability boundary completed with validated evidence."
            ),
            "used_fallback": not q3_inventory or not exec_domains or plugin_service is None,
            "upstream_degraded": not q3_inventory,
            "module_runs": list(q4_module_runs),
            "plugin_runs": [],
            "upstream_dependencies": [
                {
                    "dependency_id": "q3",
                    "required": True,
                    "status": "completed" if q3_inventory else "missing",
                    "message": "Q3 inventory is required for capability boundary evaluation.",
                }
            ],
            "recovery_plan": build_recovery_plan(
                question_id="q4",
                retriable=True,
                rollback_available=True,
                partial_retry_available=True,
                partial_replace_available=False,
                actions=[
                    build_recovery_action(
                        "q4-rerun-question",
                        label="重跑 Q4 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q4",
                        reason="重新执行能力边界评估。",
                        path="/api/web/nine-questions/q4/run",
                    ),
                    build_recovery_action(
                        "q4-refresh-capability-inputs",
                        label="刷新 Q4 能力输入模块",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q4_execution_capability_verification",
                        reason="仅刷新 Q4 inventory/permission/execution capability 模块，不重跑 LLM。",
                        path="/api/web/nine-questions/q4/modules/q4_execution_capability_verification/retry",
                    ),
                    build_recovery_action(
                        "q4-rollback-previous-success",
                        label="回滚 Q4 到上一份成功快照",
                        kind="rollback",
                        executable=True,
                        scope="question",
                        target="q4",
                        reason="当前 Q4 部分失败时，恢复上一份成功能力边界。",
                        path="/api/web/nine-questions/q4/rollback",
                    ),
                    build_recovery_action(
                        "q4-rerun-upstream-q3",
                        label="先重跑 Q3 再重跑 Q4",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q3->q4",
                        reason="Q4 的能力边界依赖 Q3 资产盘点。",
                        path="/api/web/nine-questions/q3/run",
                    ),
                ],
            ),
        }
        persist_question_module_output(
            context,
            question_id="q4",
            module_id="q4_capability_reasoning_projection",
            payload=profile.model_dump(mode="json"),
            status=str(actionability_run.get("status") or "completed"),
            output_kind="inference",
        )
        q4_module_runs = q4_execution_diagnosis.get("module_runs")
        q4_module_runs = q4_module_runs if isinstance(q4_module_runs, list) else []
        q4_payload = profile.model_dump(mode="json")
        run_audit_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            summary="Q4 能力边界裁剪审计已记录。",
            payload={
                "q4_capability_boundary_profile": q4_payload,
                "q4_capability_evidence": {
                    "q1_scene_model": upstream_context.get("q1_scene_model"),
                    "q2_role_profile": upstream_context.get("q2_role_profile"),
                    "q3_unified_asset_inventory": q3_inventory,
                },
            },
        )
        run_memory_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            title="Q4 Capability Boundary",
            summary="Q4 能力边界已写入记忆。",
            layer="episodic",
            payload=q4_payload,
            tags=["nine-questions", "q4", "capability-boundary"],
        )
        run_reflection_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            subject="Q4 capability boundary",
            summary="Q4 能力边界反思已记录。",
            reflection_type="strategy_reflection",
            payload={
                "q4_capability_boundary_profile": q4_payload,
                "q4_permission_profile": permission_profile,
            },
        )
        run_learning_integration(
            context,
            question_id="q4",
            module_runs=q4_module_runs,
            learning_kind="capability_boundary",
            summary="Q4 能力边界学习记录已登记。",
            payload=q4_payload,
        )
        q4_execution_diagnosis["module_runs"] = q4_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "capability_boundary_profile",
                    **profile.model_dump(mode="json"),
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q4_capability_boundary_profile": profile.model_dump(mode="json"),
                "q4_snapshot_version": upstream_context.get("snapshot_version"),
                "q4_active_execution_domains": exec_domains,
                "q4_permission_profile": permission_profile,
                "q4_capability_baseline": capability_baseline,
                "q4_functional_capabilities": normalized_functional_capabilities,
                "q4_execution_diagnosis": q4_execution_diagnosis,
                "q4_capability_evidence": {
                    "q1_scene_model": upstream_context.get("q1_scene_model"),
                    "q2_role_profile": upstream_context.get("q2_role_profile"),
                    "q2_mission_boundary": upstream_context.get("q2_mission_boundary"),
                    "q3_unified_asset_inventory": q3_inventory,
                    "q3_resource_evaluation": upstream_context.get("q3_resource_evaluation"),
                },
            },
            confidence=0.7,
        )


def build_q4_what_can_i_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q4,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q4WhatCanIDoPlugin:
    return Q4WhatCanIDoPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q4",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
