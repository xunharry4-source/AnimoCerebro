from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q5
from zentex.plugins.models import PluginLifecycleStatus
from plugins.nine_questions.q5_what_am_i_allowed_to_do.modules import (
    derive_authorization_baseline,
    normalize_functional_authorization_inputs,
    normalize_text,
    resolve_agent_trust_policy,
    resolve_contact_policy,
    resolve_q3_connected_agents,
    resolve_tenant_scope,
)

QUESTION_REF = "我被允许做什么"


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
    render_q4_boundary,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_prompt import build_q5_llm_request

logger = logging.getLogger(__name__)
class Q5WhatAmIAllowedToDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q5
    version: str = "2.0.0"
    feature_code: str = "nine_questions.q5"
    display_name: str = "Q5: What am I allowed to do?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Zentex Cognitive Kernel Phase 5: 我被允许做什么 (Q5: Authorization & Compliance).

    [LLM MANDATORY]: Guarantees that authorization is a semantic, non-bypassable deduction.
    """

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q5_module_runs = bind_module_runs(context, "q5")
        upstream_context = load_authoritative_question_context_from_storage(context, ["q3", "q4"])
        q4_profile = upstream_context.get("q4_capability_boundary_profile", {}) or {}
        q4_boundary_run = start_module_run(
            q5_module_runs,
            "q5_q4_boundary_validation",
            source="plugins.nine_questions.q5",
        )
        actionable_space = list(q4_profile.get("actionable_space", []) or q4_profile.get("available_actions", []) or [])
        tenant_scope = resolve_tenant_scope(upstream_context) or context.get("tenant_scope")
        tenant_scope_run = start_module_run(
            q5_module_runs,
            "q5_tenant_scope_validation",
            source="plugins.nine_questions.q5",
        )
        contact_policy = resolve_contact_policy(upstream_context) or context.get("contact_policy")
        contact_policy_run = start_module_run(
            q5_module_runs,
            "q5_contact_policy_validation",
            source="plugins.nine_questions.q5",
        )
        agent_trust_policy = resolve_agent_trust_policy(upstream_context) or context.get("agent_trust_policy")
        agent_trust_run = start_module_run(
            q5_module_runs,
            "q5_agent_trust_validation",
            source="plugins.nine_questions.q5",
        )
        q3_connected_agents = resolve_q3_connected_agents(upstream_context)
        finish_module_run(
            q4_boundary_run,
            status="completed" if q4_profile else "missing",
            error_code="" if q4_profile else "q4_boundary_missing",
            error_message="" if q4_profile else "Q4 capability boundary is missing.",
        )
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_q4_boundary_validation",
            payload={"q4_capability_boundary_profile": q4_profile},
            status=str(q4_boundary_run.get("status") or "completed"),
            output_kind="evidence",
        )
        finish_module_run(
            tenant_scope_run,
            status="completed" if tenant_scope not in (None, {}, [], "") else "missing",
            error_code="" if tenant_scope not in (None, {}, [], "") else "tenant_scope_missing",
            error_message="" if tenant_scope not in (None, {}, [], "") else "Tenant scope is not available.",
        )
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_tenant_scope_validation",
            payload={"tenant_scope": tenant_scope},
            status=str(tenant_scope_run.get("status") or "completed"),
            output_kind="evidence",
        )
        finish_module_run(
            contact_policy_run,
            status="completed" if contact_policy not in (None, {}, [], "") else "missing",
            error_code="" if contact_policy not in (None, {}, [], "") else "contact_policy_missing",
            error_message="" if contact_policy not in (None, {}, [], "") else "Contact policy is not available.",
        )
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_contact_policy_validation",
            payload={"contact_policy": contact_policy},
            status=str(contact_policy_run.get("status") or "completed"),
            output_kind="evidence",
        )
        finish_module_run(
            agent_trust_run,
            status="completed" if agent_trust_policy not in (None, {}, [], "") else "ready",
            error_code="",
            error_message="" if agent_trust_policy not in (None, {}, [], "") else "Agent trust policy is empty; continuing with neutral trust baseline.",
        )
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_agent_trust_validation",
            payload={"q5_agent_trust_status": agent_trust_policy},
            status=str(agent_trust_run.get("status") or "completed"),
            output_kind="evidence",
        )
        plugin_service = context.get("plugin_service")
        functional_authorization_inputs: list[dict[str, Any]] = []
        plugin_runs: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_authorization_inputs = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={"action_trace": dict(context)},
                trace_id=str(context.get("trace_id") or "q5"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
            for item in functional_authorization_inputs:
                plugin_runs.append(
                    {
                        "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                        "feature_code": str(item.get("feature_code") or self.feature_code),
                        "expected": True,
                        "attempted": True,
                        "status": "completed" if item.get("status") == "done" else "failed",
                        "error_code": "" if item.get("status") == "done" else "functional_authorization_failed",
                        "error_message": "" if item.get("status") == "done" else str(item.get("error") or "functional authorization input failed"),
                        "duration_ms": 0,
                        "input_summary": {},
                        "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
                    }
                )
        normalized_functional_inputs = normalize_functional_authorization_inputs(functional_authorization_inputs)
        authorization_baseline = derive_authorization_baseline(
            upstream_context,
            actionable_space,
            normalized_functional_inputs,
        )

        llm_request = build_q5_llm_request(
            authorization_baseline=authorization_baseline,
            rendered_q4_boundary=render_q4_boundary(upstream_context),
            actionable_space=actionable_space,
            snapshot_version=upstream_context.get("snapshot_version"),
            q4_capability_boundary_profile=q4_profile,
            q4_permission_profile=upstream_context.get("q4_permission_profile"),
            contact_policy=contact_policy,
            tenant_scope=tenant_scope,
            agent_trust_policy=agent_trust_policy,
            q3_connected_agents=q3_connected_agents,
            functional_authorization_inputs=normalized_functional_inputs,
        )
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        # 3. Prepare Metadata & Traceability
        trace_id = str(context.get("trace_id") or f"q5-compliance:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q5_authorization")

        # [MANDATORY] Caller Context Injection
        caller_context = build_caller_context(
            source_module="q5_what_am_i_allowed_to_do_plugin",
            invocation_phase="nine_question_q5_authorization",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        # 4. Audit Log: Trigger
        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q5_what_am_i_allowed_to_do",
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
        authorization_projection_run = start_module_run(
            q5_module_runs,
            "q5_authorization_decision_projection",
            source="plugins.nine_questions.q5",
        )

        # 5. Execute LLM Inference with Fail-Closed Block
        try:
            raw = provider.generate_json(
                prompt=prompt,
                context=model_context,
                caller_context=caller_context
            )
        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q5_what_am_i_allowed_to_do",
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
                authorization_projection_run,
                error_code="q5_llm_invocation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q5",
                question_ref=QUESTION_REF,
                error_code="q5_llm_invocation_failed",
                error_message=str(exc),
                diagnosis_key="q5_execution_diagnosis",
                module_runs=list(q5_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[{"dependency_id": "q4", "required": True, "status": "completed" if q4_profile else "missing"}],
                context_updates={
                    "q5_authorization_baseline": authorization_baseline,
                    "q5_functional_authorization_inputs": normalized_functional_inputs,
                },
                required_modules=["q5_q4_boundary_validation", "q5_authorization_decision_projection"],
            )

        profile = None
        permission_boundary = None
        if isinstance(raw, dict):
            profile = raw.get("authorization_boundary_profile")
            permission_boundary = raw.get("permission_boundary")
            if not isinstance(profile, dict) and isinstance(permission_boundary, dict):
                allowed = list(permission_boundary.get("authorized_actions", []) or [])
                if actionable_space:
                    allowed = [action for action in allowed if str(action) in set(map(str, actionable_space))]
                forbidden_actions = [
                    {"action": action, "reason": "explicitly unauthorized"}
                    for action in list(permission_boundary.get("unauthorized_actions", []) or [])
                ]
                profile = {
                    "allowed_action_space": allowed,
                    "forbidden_action_space": forbidden_actions,
                    "contact_and_org_boundaries": {},
                    "requires_escalation_actions": list(permission_boundary.get("conditional_actions", []) or []),
                }
        if not isinstance(profile, dict):
            fail_module_run(
                authorization_projection_run,
                error_code="q5_output_validation_failed",
                error_message="Invalid Q5 output: missing authorization_boundary_profile",
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q5",
                question_ref=QUESTION_REF,
                error_code="q5_output_validation_failed",
                error_message="Invalid Q5 output: missing authorization_boundary_profile",
                diagnosis_key="q5_execution_diagnosis",
                module_runs=list(q5_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[{"dependency_id": "q4", "required": True, "status": "completed" if q4_profile else "missing"}],
                context_updates={"q5_authorization_baseline": authorization_baseline},
                required_modules=["q5_authorization_decision_projection"],
            )
        allowed = profile.get("allowed_action_space")
        if not isinstance(allowed, list):
            fail_module_run(
                authorization_projection_run,
                error_code="q5_output_validation_failed",
                error_message="Invalid Q5 output: allowed_action_space must be a list",
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q5",
                question_ref=QUESTION_REF,
                error_code="q5_output_validation_failed",
                error_message="Invalid Q5 output: allowed_action_space must be a list",
                diagnosis_key="q5_execution_diagnosis",
                module_runs=list(q5_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[{"dependency_id": "q4", "required": True, "status": "completed" if q4_profile else "missing"}],
                context_updates={"q5_authorization_baseline": authorization_baseline},
                required_modules=["q5_authorization_decision_projection"],
            )

        baseline_allowed = authorization_baseline.get("allowed_action_space") or []
        baseline_allowed_set = set(map(str, baseline_allowed))
        allowed = [action for action in map(str, allowed) if action in set(map(str, actionable_space))]
        if baseline_allowed_set:
            allowed = [action for action in allowed if action in baseline_allowed_set]
        merged_allowed = list(dict.fromkeys(list(map(str, allowed)) + list(map(str, baseline_allowed))))

        baseline_forbidden = authorization_baseline.get("forbidden_action_space") or []
        forbidden_payload = profile.get("forbidden_action_space") or []
        merged_forbidden: list[dict[str, str]] = []
        for item in list(forbidden_payload) + list(baseline_forbidden):
            if not isinstance(item, dict):
                continue
            action = normalize_text(item.get("action"))
            reason = normalize_text(item.get("reason")) or "unauthorized"
            if action:
                merged_forbidden.append({"action": action, "reason": reason})
        merged_forbidden = list(
            {
                (item["action"], item["reason"]): item
                for item in merged_forbidden
            }.values()
        )

        merged_escalations = list(
            dict.fromkeys(
                [
                    str(item).strip()
                    for item in (
                        list(profile.get("requires_escalation_actions") or [])
                        + list(authorization_baseline.get("requires_escalation_actions") or [])
                    )
                    if str(item).strip()
                ]
            )
        )
        merged_contact_boundaries = authorization_baseline.get("contact_and_org_boundaries") or {}
        if isinstance(profile.get("contact_and_org_boundaries"), dict):
            merged_contact_boundaries = {
                **merged_contact_boundaries,
                **profile.get("contact_and_org_boundaries"),
            }
        profile = {
            "allowed_action_space": merged_allowed,
            "forbidden_action_space": merged_forbidden,
            "contact_and_org_boundaries": merged_contact_boundaries,
            "requires_escalation_actions": merged_escalations,
        }
        if not set(map(str, profile.get("allowed_action_space", []))).issubset(set(map(str, actionable_space))):
            fail_module_run(
                authorization_projection_run,
                error_code="q5_authorization_violation",
                error_message="Q5 authorization violation: allowed_action_space exceeds Q4 actionable_space",
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q5",
                question_ref=QUESTION_REF,
                error_code="q5_authorization_violation",
                error_message="Q5 authorization violation: allowed_action_space exceeds Q4 actionable_space",
                diagnosis_key="q5_execution_diagnosis",
                module_runs=list(q5_module_runs),
                plugin_runs=plugin_runs,
                upstream_dependencies=[{"dependency_id": "q4", "required": True, "status": "completed" if q4_profile else "missing"}],
                context_updates={"q5_authorization_baseline": authorization_baseline},
                required_modules=["q5_authorization_decision_projection"],
            )
        normalized_permission_boundary = {
            "authorized_actions": list(profile.get("allowed_action_space", []) or []),
            "unauthorized_actions": [
                str(item.get("action"))
                for item in list(profile.get("forbidden_action_space", []) or [])
                if isinstance(item, dict) and str(item.get("action") or "").strip()
            ],
            "conditional_actions": list(profile.get("requires_escalation_actions", []) or []),
        }
        validated_policy_sources = sum(
            1
            for payload in (tenant_scope, contact_policy, agent_trust_policy)
            if payload not in (None, {}, [], "")
        )
        authenticity_status = (
            "completed"
            if q4_profile and validated_policy_sources >= 2 and plugin_service is not None
            else "degraded"
        )
        finish_module_run(
            authorization_projection_run,
            status="completed" if authenticity_status == "completed" else "degraded",
            error_code="" if authenticity_status == "completed" else "authorization_projection_degraded",
            error_message="" if authenticity_status == "completed" else "Authorization actions were produced without enough validated policy sources.",
        )
        q5_execution_diagnosis = {
            "authenticity_status": authenticity_status,
            "diagnosis_code": "authorization_boundary_degraded" if authenticity_status != "completed" else "completed",
            "diagnosis_message": (
                "Q5 authorization boundary relies on snapshot-only policy sources or missing functional authorization inputs."
                if authenticity_status != "completed"
                else "Q5 authorization boundary completed with validated upstream and policy evidence."
            ),
            "used_fallback": authenticity_status != "completed",
            "upstream_degraded": not bool(q4_profile),
            "module_runs": list(q5_module_runs),
            "plugin_runs": plugin_runs,
            "upstream_dependencies": [
                {
                    "dependency_id": "q4",
                    "required": True,
                    "status": "completed" if q4_profile else "missing",
                    "message": "Q4 capability boundary is required for authorization projection.",
                }
            ],
            "recovery_plan": build_recovery_plan(
                question_id="q5",
                retriable=True,
                rollback_available=False,
                partial_retry_available=True,
                partial_replace_available=False,
                actions=[
                    build_recovery_action(
                        "q5-rerun-question",
                        label="重跑 Q5 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q5",
                        reason="重新执行授权边界判断。",
                        path="/api/web/nine-questions/q5/run",
                    ),
                    build_recovery_action(
                        "q5-rerun-upstream-q4",
                        label="先重跑 Q4 再重跑 Q5",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q4->q5",
                        reason="Q5 依赖 Q4 能力边界。",
                        path="/api/web/nine-questions/q4/run",
                    ),
                    build_recovery_action(
                        "q5-refresh-contact-policy",
                        label="刷新 contact policy",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q5_contact_policy_validation",
                        reason="仅刷新 Q5 contact_policy 基线与模块状态，不重跑 LLM。",
                        path="/api/web/nine-questions/q5/modules/q5_contact_policy_validation/retry",
                    ),
                ],
            ),
        }
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_authorization_decision_projection",
            payload={
                "authorization_boundary_profile": profile,
                "permission_boundary": normalized_permission_boundary,
            },
            status=str(authorization_projection_run.get("status") or "completed"),
            output_kind="inference",
        )

        # 7. Audit Log: Completion
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q5_what_am_i_allowed_to_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": raw,
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
            },
        )

        summary = f"allowed={len(profile.get('allowed_action_space', []) or [])}; forbidden={len(profile.get('forbidden_action_space', []) or [])}"
        q5_module_runs = q5_execution_diagnosis.get("module_runs")
        q5_module_runs = q5_module_runs if isinstance(q5_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            summary="Q5 授权裁剪审计已记录。",
            payload={
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
                "q5_authorization_baseline": authorization_baseline,
            },
        )
        run_memory_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            title="Q5 Authorization Boundary",
            summary="Q5 授权边界已写入记忆。",
            layer="episodic",
            payload=profile,
            tags=["nine-questions", "q5", "authorization-boundary"],
        )
        run_reflection_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            subject="Q5 authorization boundary",
            summary="Q5 越权风险与裁剪充分性反思已记录。",
            reflection_type="decision_reflection",
            payload={
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
            },
        )
        run_learning_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            learning_kind="authorization_boundary",
            summary="Q5 授权决策学习记录已登记。",
            payload=profile,
        )
        q5_execution_diagnosis["module_runs"] = q5_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "authorization_boundary_profile",
                    **profile,
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
                "q5_authorization_baseline": authorization_baseline,
                "q5_agent_trust_status": authorization_baseline.get("agent_trust_status", {}),
                "q5_functional_authorization_inputs": normalized_functional_inputs,
                "q5_execution_diagnosis": q5_execution_diagnosis,
            },
            confidence=0.9,
        )


def build_q5_what_am_i_allowed_to_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q5,
    version: str = "2.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q5WhatAmIAllowedToDoPlugin:
    return Q5WhatAmIAllowedToDoPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q5",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
