from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q5
from zentex.plugins.models import PluginLifecycleStatus

QUESTION_REF = "我被允许做什么"


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_q4_boundary,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_prompt import build_q5_llm_request

logger = logging.getLogger(__name__)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _normalize_functional_authorization_inputs(
    functional_authorization_inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in functional_authorization_inputs:
        if not isinstance(item, dict) or item.get("status") != "done":
            continue
        normalized.append(
            {
                "plugin_id": _normalize_text(item.get("plugin_id")),
                "status": _normalize_text(item.get("status")) or "done",
                "result": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
    return normalized


def _derive_agent_trust_status(snapshot: dict[str, Any]) -> dict[str, str]:
    trust_policy = snapshot.get("agent_trust_policy")
    if isinstance(trust_policy, dict):
        return {
            str(key): str(value)
            for key, value in trust_policy.items()
            if _normalize_text(key) and _normalize_text(value)
        }

    connected_agents = snapshot.get("q3_connected_agents")
    if not isinstance(connected_agents, list):
        connected_agents = []
    derived: dict[str, str] = {}
    for agent in connected_agents:
        if not isinstance(agent, dict):
            continue
        agent_id = _normalize_text(agent.get("agent_id") or agent.get("id") or agent.get("name"))
        trust = _normalize_text(agent.get("trust_level") or agent.get("status") or agent.get("scope"))
        if agent_id and trust:
            derived[agent_id] = trust
    return derived


def _derive_authorization_baseline(
    snapshot: dict[str, Any],
    actionable_space: list[str],
    normalized_functional_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    permission_profile = snapshot.get("q4_permission_profile")
    permission_profile = permission_profile if isinstance(permission_profile, dict) else {}
    contact_policy = snapshot.get("contact_policy")
    contact_policy = contact_policy if isinstance(contact_policy, dict) else {}
    tenant_scope = snapshot.get("tenant_scope")
    tenant_scope = tenant_scope if isinstance(tenant_scope, dict) else {}
    trust_status = _derive_agent_trust_status(snapshot)

    mode = _normalize_text(permission_profile.get("mode")) or "unknown"
    requires_human_confirmation = bool(permission_profile.get("is_read_only"))
    requires_cloud_audit = False

    allowed_action_space: list[str] = []
    forbidden_action_space: list[dict[str, str]] = []
    requires_escalation_actions: list[str] = []
    contact_and_org_boundaries: dict[str, Any] = {
        "execution_tier": "constrained_execute",
        "interaction_scope": "whitelist_only",
        "requires_human_confirmation": requires_human_confirmation,
        "requires_cloud_audit": requires_cloud_audit,
    }

    if mode == "read_only":
        contact_and_org_boundaries["execution_tier"] = "read_only"
        allowed_action_space = [
            action for action in actionable_space if "read" in action.lower() or "inspect" in action.lower()
        ]
        for action in actionable_space:
            if action not in allowed_action_space:
                forbidden_action_space.append({"action": action, "reason": "read_only boundary"})
                requires_escalation_actions.append(action)
    else:
        allowed_action_space = list(actionable_space)

    if tenant_scope:
        contact_and_org_boundaries["tenant_scope"] = tenant_scope
        if tenant_scope.get("same_org_only") is True:
            contact_and_org_boundaries["interaction_scope"] = "same_org_only"
        if isinstance(tenant_scope.get("forbidden_actions"), list):
            forbidden_set = {_normalize_text(item) for item in tenant_scope.get("forbidden_actions") if _normalize_text(item)}
            retained_allowed: list[str] = []
            for action in allowed_action_space:
                if action in forbidden_set:
                    forbidden_action_space.append({"action": action, "reason": "tenant scope forbidden"})
                else:
                    retained_allowed.append(action)
            allowed_action_space = retained_allowed

    if contact_policy:
        contact_and_org_boundaries["contact_policy"] = contact_policy
        if contact_policy.get("requires_human_confirmation") is True:
            requires_human_confirmation = True
            contact_and_org_boundaries["requires_human_confirmation"] = True
        if contact_policy.get("requires_cloud_audit") is True:
            requires_cloud_audit = True
            contact_and_org_boundaries["requires_cloud_audit"] = True
        blocked_contacts = _coerce_string_list(contact_policy.get("blocked_actions"))
        if blocked_contacts:
            retained_allowed = []
            blocked_set = set(blocked_contacts)
            for action in allowed_action_space:
                if action in blocked_set:
                    forbidden_action_space.append({"action": action, "reason": "contact policy blocked"})
                else:
                    retained_allowed.append(action)
            allowed_action_space = retained_allowed

    if trust_status:
        contact_and_org_boundaries["agent_trust_status"] = trust_status
        if any(status.lower() in {"pending", "revoked", "blocked"} for status in trust_status.values()):
            requires_human_confirmation = True
            contact_and_org_boundaries["requires_human_confirmation"] = True

    for item in normalized_functional_inputs:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if not result:
            continue
        if isinstance(result.get("forbidden_actions"), list):
            for action in result.get("forbidden_actions", []):
                text = _normalize_text(action)
                if text:
                    forbidden_action_space.append({"action": text, "reason": f"functional policy {item.get('plugin_id')}"})
        if isinstance(result.get("requires_escalation_actions"), list):
            requires_escalation_actions.extend(_coerce_string_list(result.get("requires_escalation_actions")))

    forbidden_index = {
        (_normalize_text(item.get("action")), _normalize_text(item.get("reason"))): item
        for item in forbidden_action_space
        if _normalize_text(item.get("action"))
    }
    forbidden_action_space = list(forbidden_index.values())
    requires_escalation_actions = list(dict.fromkeys(action for action in requires_escalation_actions if _normalize_text(action)))
    allowed_action_space = [
        action
        for action in list(dict.fromkeys(actionable for actionable in allowed_action_space if _normalize_text(actionable)))
        if action not in {item["action"] for item in forbidden_action_space}
    ]

    return {
        "allowed_action_space": allowed_action_space,
        "forbidden_action_space": forbidden_action_space,
        "contact_and_org_boundaries": contact_and_org_boundaries,
        "requires_escalation_actions": requires_escalation_actions,
        "agent_trust_status": trust_status,
    }


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
        snapshot = context.get("context_snapshot", {}) or {}
        if not snapshot and any(key.startswith("q") or key in {"contact_policy", "tenant_scope", "agent_trust_policy"} for key in context):
            snapshot = dict(context)
        q4_profile = snapshot.get("q4_capability_boundary_profile", {}) or {}
        actionable_space = list(q4_profile.get("actionable_space", []) or q4_profile.get("available_actions", []) or [])
        plugin_service = context.get("plugin_service")
        functional_authorization_inputs: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_authorization_inputs = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={"action_trace": dict(context)},
                trace_id=str(context.get("trace_id") or "q5"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
        normalized_functional_inputs = _normalize_functional_authorization_inputs(functional_authorization_inputs)
        authorization_baseline = _derive_authorization_baseline(
            snapshot,
            actionable_space,
            normalized_functional_inputs,
        )

        llm_request = build_q5_llm_request(
            authorization_baseline=authorization_baseline,
            rendered_q4_boundary=render_q4_boundary(snapshot),
            actionable_space=actionable_space,
            snapshot_version=snapshot.get("snapshot_version"),
            q4_capability_boundary_profile=q4_profile,
            q4_permission_profile=snapshot.get("q4_permission_profile"),
            contact_policy=snapshot.get("contact_policy"),
            tenant_scope=snapshot.get("tenant_scope"),
            agent_trust_policy=snapshot.get("agent_trust_policy"),
            q3_connected_agents=snapshot.get("q3_connected_agents"),
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
            raise

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
            raise ValueError("Invalid Q5 output: missing authorization_boundary_profile")
        allowed = profile.get("allowed_action_space")
        if not isinstance(allowed, list):
            raise ValueError("Invalid Q5 output: allowed_action_space must be a list")

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
            action = _normalize_text(item.get("action"))
            reason = _normalize_text(item.get("reason")) or "unauthorized"
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
                _coerce_string_list(profile.get("requires_escalation_actions"))
                + _coerce_string_list(authorization_baseline.get("requires_escalation_actions"))
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
            raise RuntimeError("Q5 authorization violation: allowed_action_space exceeds Q4 actionable_space")
        normalized_permission_boundary = {
            "authorized_actions": list(profile.get("allowed_action_space", []) or []),
            "unauthorized_actions": [
                str(item.get("action"))
                for item in list(profile.get("forbidden_action_space", []) or [])
                if isinstance(item, dict) and str(item.get("action") or "").strip()
            ],
            "conditional_actions": list(profile.get("requires_escalation_actions", []) or []),
        }

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
