from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q5
from zentex.plugins.models import PluginLifecycleStatus
from plugins.nine_questions.q3_role_inference.llm_output_table import (
    load_llm_output_from_table as load_q3_llm_output_from_table,
)
from plugins.nine_questions.q4_what_can_i_do.llm_output_table import (
    load_q4_internal_inferred_capabilities,
    load_llm_output_from_table as load_q4_llm_output_from_table,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.internal import (
    derive_authorization_baseline,
    derive_authorization_input_projection,
    normalize_text,
    coerce_string_list,
    resolve_workspace_forbidden_actions,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.external import (
    load_q2_external_connected_agents,
    run_external_authorization_inputs,
)

QUESTION_REF = "我不能干什么"


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
    render_q4_boundary,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_prompt import build_q5_llm_request
from plugins.nine_questions.q5_what_am_i_allowed_to_do.models import AuthorizationBoundary, AuthorizationBoundaryEnvelope

logger = logging.getLogger(__name__)


def _authorization_boundary_dump(boundary: AuthorizationBoundary) -> dict[str, Any]:
    return {"AuthorizationBoundary": boundary.model_dump(mode="json")}


def _derive_q5_profile_projection(
    boundary: AuthorizationBoundary,
    authorization_baseline: dict[str, Any],
    question_driver_refs: list[str],
) -> dict[str, Any]:
    baseline_forbidden = authorization_baseline.get("forbidden_action_space") or []
    forbidden_actions = [
        {"action": action, "reason": "AuthorizationBoundary.forbidden_operations"}
        for action in boundary.forbidden_operations
    ]
    for item in baseline_forbidden:
        if isinstance(item, dict):
            action = normalize_text(item.get("action"))
            reason = normalize_text(item.get("reason")) or "authorization baseline"
            if action:
                forbidden_actions.append({"action": action, "reason": reason})
        else:
            action = normalize_text(item)
            if action:
                forbidden_actions.append({"action": action, "reason": "authorization baseline"})
    forbidden_actions = list(
        {
            (item["action"], item["reason"]): item
            for item in forbidden_actions
            if normalize_text(item.get("action"))
        }.values()
    )
    contact_boundaries = dict(authorization_baseline.get("contact_and_org_boundaries") or {})
    contact_boundaries.update(
        {
            "current_authorization_scope": boundary.current_authorization_scope,
            "communication_policy": boundary.communication_policy,
            "organizational_boundary": boundary.organizational_boundary,
            "contact_policies": [boundary.communication_policy],
            "organizational_boundaries": boundary.organizational_boundary,
        }
    )
    return {
        "current_authorization_scope": boundary.current_authorization_scope,
        "communication_policy": boundary.communication_policy,
        "organizational_boundary": boundary.organizational_boundary,
        "allowed_operations": list(boundary.allowed_operations),
        "forbidden_operations": list(boundary.forbidden_operations),
        "contact_policies": [boundary.communication_policy],
        "organizational_boundaries": boundary.organizational_boundary,
        "allowed_actions": list(boundary.allowed_operations),
        "forbidden_actions": list(boundary.forbidden_operations),
        "question_driver_refs": list(question_driver_refs),
        "allowed_action_space": list(boundary.allowed_operations),
        "forbidden_action_space": forbidden_actions,
        "contact_and_org_boundaries": contact_boundaries,
        "requires_escalation_actions": list(authorization_baseline.get("requires_escalation_actions") or []),
    }


def _coerce_unique_list(value: Any) -> list[str]:
    seen: dict[str, None] = {}
    for raw_item in coerce_string_list(value):
        item = normalize_text(raw_item)
        if item and item not in seen:
            seen[item] = None
    return list(seen.keys())


def _derive_internal_q4_capability_profile(
    q4_profile: dict[str, Any],
    internal_inferred_capabilities: list[dict[str, Any]],
) -> dict[str, Any]:
    internal_names = _coerce_unique_list(
        [
            item.get("capability_name")
            for item in internal_inferred_capabilities
            if isinstance(item, dict)
        ]
    )
    if not internal_names:
        return dict(q4_profile)

    internal_set = set(internal_names)
    projected = dict(q4_profile)

    upper_limits = _coerce_unique_list(
        [
            item
            for item in coerce_string_list(projected.get("capability_upper_limits", []))
            if normalize_text(item) in internal_set
        ]
        or internal_names
    )
    actionable_space = _coerce_unique_list(
        [
            item
            for item in coerce_string_list(projected.get("actionable_space", []))
            if normalize_text(item) in internal_set
        ]
        or internal_names
    )
    executable_strategies = _coerce_unique_list(
        [
            item
            for item in coerce_string_list(projected.get("executable_strategies", []))
            if normalize_text(item) in internal_set
        ]
        or internal_names
    )

    projected["capability_upper_limits"] = upper_limits
    projected["actionable_space"] = actionable_space
    projected["executable_strategies"] = executable_strategies
    projected["provenance"] = {
        "internal_inferred_capability_count": len(internal_inferred_capabilities),
        "internal_inferred_capability_names": internal_names,
    }
    projected["source_q4_capability_inference"] = "internal"
    return projected


def _derive_q5_permission_boundary(profile: dict[str, Any]) -> dict[str, Any]:
    unauthorized_actions: list[str] = []
    unauthorized_actions.extend(coerce_string_list(profile.get("forbidden_actions")))
    forbidden_action_space = profile.get("forbidden_action_space")
    if isinstance(forbidden_action_space, list):
        for item in forbidden_action_space:
            if isinstance(item, dict):
                action = normalize_text(item.get("action"))
                reason = normalize_text(item.get("reason"))
                if action and reason:
                    unauthorized_actions.append(f"{action}: {reason}")
                elif action:
                    unauthorized_actions.append(action)
            else:
                unauthorized_actions.extend(coerce_string_list(item))
    unauthorized_actions = list(dict.fromkeys(action for action in unauthorized_actions if normalize_text(action)))

    return {
        "authorized_actions": list(profile.get("allowed_actions") or profile.get("allowed_action_space") or []),
        "unauthorized_actions": unauthorized_actions,
        "conditional_actions": list(profile.get("requires_escalation_actions") or []),
    }


def _derive_q5_convergence_guard(boundary: AuthorizationBoundary, profile: dict[str, Any]) -> dict[str, Any]:
    combined_text = " ".join(
        [
            boundary.current_authorization_scope,
            boundary.organizational_boundary,
            boundary.communication_policy,
        ]
    ).lower()
    collaboration_unavailable = any(
        token in combined_text
        for token in ("协作不可用", "禁止协作", "不得协作", "disabled", "unavailable", "blocked", "revoked", "none")
    )
    authorization_limited = False
    return {
        "collaboration_available": not collaboration_unavailable,
        "authorization_limited": authorization_limited,
        "objective_scope": "single_brain_only" if collaboration_unavailable else "authorized_collaboration_allowed",
        "q8_rule": "Q8 must shrink objectives to single-brain achievable goals when collaboration is unavailable.",
        "q9_rule": "Q9 must treat Q5 forbidden_operations as authorization red lines for posture and dispatch.",
        "source_refs": list(profile.get("question_driver_refs") or []),
        "forbidden_action_count": len(profile.get("forbidden_action_space") or []),
    }


class Q5WhatAmIAllowedToDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q5
    version: str = "2.0.0"
    feature_code: str = "nine_questions.q5"
    display_name: str = "Q5: What can I not do?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Zentex Cognitive Kernel Phase 5: 我不能干什么 (Q5: Cannot-do boundary and compliance).

    [LLM MANDATORY]: Guarantees that authorization is a semantic, non-bypassable deduction.
    """

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        q5_module_runs = bind_module_runs(context, "q5")
        upstream_context = {
            **load_q3_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
            **load_q4_llm_output_from_table(db_path=context.get("nine_question_state_db_path")),
        }
        q4_profile = upstream_context.get("q4_capability_boundary_profile", {}) or {}
        q4_internal_inferred_capabilities = load_q4_internal_inferred_capabilities(
            db_path=context.get("nine_question_state_db_path"),
            session_id=context.get("session_id") or "nq-baseline",
        )
        q4_profile = _derive_internal_q4_capability_profile(
            q4_profile,
            q4_internal_inferred_capabilities,
        )
        upstream_context["q4_internal_inferred_capabilities"] = q4_internal_inferred_capabilities
        actionable_space = list(q4_profile.get("actionable_space", []) or q4_profile.get("available_actions", []) or [])
        identity_kernel = upstream_context.get("identity_kernel_snapshot")
        if not isinstance(identity_kernel, dict):
            identity_kernel = {}
        if not identity_kernel:
            q3_role_profile = upstream_context.get("q3_role_profile")
            q3_mission_boundary = upstream_context.get("q3_mission_boundary")
            identity_kernel = {
                "q3_role_profile": q3_role_profile if isinstance(q3_role_profile, dict) else {},
                "q3_mission_boundary": q3_mission_boundary if isinstance(q3_mission_boundary, dict) else {},
            }
        tenant_scope = upstream_context.get("tenant_scope")
        contact_policy = upstream_context.get("contact_policy")
        agent_trust_policy = upstream_context.get("agent_trust_policy")
        authorization_inputs = derive_authorization_input_projection(upstream_context)
        if tenant_scope in (None, {}, [], ""):
            tenant_scope = authorization_inputs.get("tenant_scope")
        if contact_policy in (None, {}, [], ""):
            contact_policy = authorization_inputs.get("contact_policy")
        if agent_trust_policy in (None, {}, [], ""):
            agent_trust_policy = authorization_inputs.get("agent_trust_policy")
        workspace_forbidden_actions = resolve_workspace_forbidden_actions(context)
        if workspace_forbidden_actions:
            tenant_scope = dict(tenant_scope) if isinstance(tenant_scope, dict) else {}
            tenant_scope["forbidden_actions"] = list(
                dict.fromkeys([
                    *coerce_string_list(tenant_scope.get("forbidden_actions")),
                    *workspace_forbidden_actions,
                ])
            )
        plugin_service = context.get("plugin_service")
        missing_inputs: list[str] = []
        if not identity_kernel or not any(identity_kernel.values()):
            missing_inputs.append("identity_kernel")
        if not q4_profile:
            missing_inputs.append("q4_capability_boundary_profile")
        if tenant_scope in (None, {}, [], ""):
            missing_inputs.append("tenant_scope")
        if contact_policy in (None, {}, [], ""):
            missing_inputs.append("contact_policy")
        if agent_trust_policy in (None, {}, [], ""):
            missing_inputs.append("agent_trust_policy")
        if plugin_service is None:
            missing_inputs.append("plugin_service")
        if missing_inputs:
            raise RuntimeError("Q5 authorization inputs are incomplete: " + ", ".join(missing_inputs))
        authorization_context = dict(upstream_context)
        authorization_context["tenant_scope"] = tenant_scope
        authorization_context["contact_policy"] = contact_policy
        authorization_context["agent_trust_policy"] = agent_trust_policy
        if workspace_forbidden_actions:
            authorization_context["workspace_forbidden_actions"] = workspace_forbidden_actions

        q4_boundary_run = start_module_run(
            q5_module_runs,
            "q5_q4_boundary_validation",
            source="plugins.nine_questions.q5",
        )
        tenant_scope_run = start_module_run(
            q5_module_runs,
            "q5_tenant_scope_validation",
            source="plugins.nine_questions.q5",
        )
        contact_policy_run = start_module_run(
            q5_module_runs,
            "q5_contact_policy_validation",
            source="plugins.nine_questions.q5",
        )
        agent_trust_run = start_module_run(
            q5_module_runs,
            "q5_agent_trust_validation",
            source="plugins.nine_questions.q5",
        )
        q2_connected_agents = load_q2_external_connected_agents(context)
        finish_module_run(q4_boundary_run)
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_q4_boundary_validation",
            payload={"q4_capability_boundary_profile": q4_profile},
            status=str(q4_boundary_run.get("status") or "completed"),
            output_kind="evidence",
        )
        finish_module_run(tenant_scope_run)
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_tenant_scope_validation",
            payload={
                "tenant_scope": tenant_scope,
                "workspace_forbidden_actions": workspace_forbidden_actions,
            },
            status=str(tenant_scope_run.get("status") or "completed"),
            output_kind="evidence",
        )
        finish_module_run(contact_policy_run)
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_contact_policy_validation",
            payload={"contact_policy": contact_policy},
            status=str(contact_policy_run.get("status") or "completed"),
            output_kind="evidence",
        )
        finish_module_run(agent_trust_run)
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_agent_trust_validation",
            payload={"q5_agent_trust_status": agent_trust_policy},
            status=str(agent_trust_run.get("status") or "completed"),
            output_kind="evidence",
        )
        normalized_functional_inputs, plugin_runs = run_external_authorization_inputs(
            plugin_service,
            plugin_id=self.plugin_id,
            feature_code=self.feature_code,
            context=context,
        )
        authorization_baseline = derive_authorization_baseline(
            authorization_context,
            actionable_space,
            normalized_functional_inputs,
        )
        question_driver_refs = [
            str(item or "").strip()
            for item in (context.get("question_driver_refs") or [])
            if str(item or "").strip()
        ]
        for ref in (
            "q3.identity_kernel",
            "q4.capability_boundary_profile",
            "q4.permission_profile",
            "q5.tenant_scope",
            "q5.contact_policy",
            "q5.agent_trust_policy",
        ):
            if ref not in question_driver_refs:
                question_driver_refs.append(ref)
        if workspace_forbidden_actions and "settings.workspace_forbidden_actions" not in question_driver_refs:
            question_driver_refs.append("settings.workspace_forbidden_actions")

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
            q2_connected_agents=q2_connected_agents,
            functional_authorization_inputs=normalized_functional_inputs,
            identity_kernel=identity_kernel,
            question_driver_refs=question_driver_refs,
        )
        system_prompt = llm_request["system_prompt"]
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
            question_driver_refs=question_driver_refs,
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
                "system_prompt": system_prompt,
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
            started = perf_counter()
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
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
            raise RuntimeError(f"Q5 LLM invocation failed: {exc}") from exc

        try:
            boundary = AuthorizationBoundaryEnvelope.model_validate(raw).AuthorizationBoundary
        except Exception as exc:
            fail_module_run(
                authorization_projection_run,
                error_code="q5_output_validation_failed",
                error_message=str(exc),
            )
            raise RuntimeError("Invalid Q5 output: AuthorizationBoundary validation failed") from exc
        allowed_set = set(map(str, actionable_space))
        invalid_allowed = [action for action in boundary.allowed_operations if action not in allowed_set]
        if invalid_allowed:
            fail_module_run(
                authorization_projection_run,
                error_code="q5_authorization_violation",
                error_message=f"Q5 authorization violation: allowed_operations exceed Q4 actionable_space: {invalid_allowed}",
            )
            raise RuntimeError("Q5 authorization violation: allowed_operations exceed Q4 actionable_space")
        profile = _derive_q5_profile_projection(boundary, authorization_baseline, question_driver_refs)
        authorization_boundary = _authorization_boundary_dump(boundary)
        normalized_permission_boundary = _derive_q5_permission_boundary(profile)
        convergence_guard = _derive_q5_convergence_guard(boundary, profile)
        validated_policy_sources = sum(
            1
            for payload in (tenant_scope, contact_policy, agent_trust_policy)
            if payload not in (None, {}, [], "")
        )
        if not (q4_profile and validated_policy_sources >= 3 and plugin_service is not None):
            raise RuntimeError("Q5 authorization evidence is incomplete")
        authenticity_status = "completed"
        finish_module_run(
            authorization_projection_run,
            status="completed",
        )
        q5_execution_diagnosis = {
            "authenticity_status": authenticity_status,
            "diagnosis_code": "completed",
            "diagnosis_message": "Q5 cannot-do boundary completed with validated upstream and policy evidence.",
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
                        reason="重新执行禁止边界判断。",
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
                "authorization_boundary": authorization_boundary,
                "authorization_boundary_profile": profile,
                "permission_boundary": normalized_permission_boundary,
                "q5_objective_convergence_guard": convergence_guard,
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
                "result": authorization_boundary,
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": elapsed_ms,
            },
        )

        llm_trace_payload = {
            "request_id": request_id,
            "decision_id": decision_id,
            "provider_name": safe_provider_plugin_id(provider),
            "model": json_safe_payload(getattr(provider, "last_model_name", None)),
            "system_prompt": system_prompt,
            "prompt": prompt,
            "source_module": "q5_what_am_i_allowed_to_do_plugin",
            "invocation_phase": "nine_question_q5_authorization",
            "question_driver_refs": list(caller_context.question_driver_refs),
            "context_data": model_context,
            "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
            "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)) or {},
            "elapsed_ms": elapsed_ms,
        }
        summary = f"allowed={len(profile.get('allowed_action_space', []) or [])}; forbidden={len(profile.get('forbidden_action_space', []) or [])}"
        q5_module_runs = q5_execution_diagnosis.get("module_runs")
        q5_module_runs = q5_module_runs if isinstance(q5_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            summary="Q5 授权裁剪审计已记录。",
            payload={
                "q5_authorization_boundary": authorization_boundary,
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
                "q5_authorization_baseline": authorization_baseline,
                "q5_objective_convergence_guard": convergence_guard,
                "llm_trace_payload": llm_trace_payload,
            },
        )
        run_memory_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            title="Q5 Cannot-Do Boundary",
            summary="Q5 禁止边界已写入记忆。",
            layer="episodic",
            payload={
                "q5_authorization_boundary": authorization_boundary,
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
                "q5_objective_convergence_guard": convergence_guard,
                "llm_trace_payload": llm_trace_payload,
            },
            tags=["nine-questions", "q5", "authorization-boundary"],
        )
        run_reflection_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            subject="Q5 cannot-do boundary",
            summary="Q5 越权风险与裁剪充分性反思已记录。",
            reflection_type="decision_reflection",
            payload={
                "q5_authorization_boundary": authorization_boundary,
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
                "q5_objective_convergence_guard": convergence_guard,
            },
        )
        run_learning_integration(
            context,
            question_id="q5",
            module_runs=q5_module_runs,
            learning_kind="authorization_boundary",
            summary="Q5 授权决策学习记录已登记。",
            payload={
                "q5_authorization_boundary": authorization_boundary,
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
                "q5_objective_convergence_guard": convergence_guard,
            },
        )
        q5_execution_diagnosis["module_runs"] = q5_module_runs

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "authorization_boundary",
                    **authorization_boundary,
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q4_capability_boundary_profile": q4_profile,
                "authorization_boundary": authorization_boundary,
                "q5_authorization_boundary": authorization_boundary,
                "q5_authorization_boundary_profile": profile,
                "q5_permission_boundary": normalized_permission_boundary,
                "q5_authorization_baseline": authorization_baseline,
                "q5_objective_convergence_guard": convergence_guard,
                "q5_agent_trust_status": authorization_baseline.get("agent_trust_status", {}),
                "q5_functional_authorization_inputs": normalized_functional_inputs,
                "q5_execution_diagnosis": q5_execution_diagnosis,
                "llm_trace_payload": llm_trace_payload,
            },
            llm_trace_payload=llm_trace_payload,
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
