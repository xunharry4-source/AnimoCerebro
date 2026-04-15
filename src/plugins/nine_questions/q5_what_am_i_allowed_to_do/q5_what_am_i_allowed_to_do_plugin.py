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

        prompt = (
            "You are Zentex. Determine what actions are authorized (Q5: 我被允许做什么).\n\n"
            "Return STRICT JSON with the top-level key: authorization_boundary_profile.\n"
            "authorization_boundary_profile MUST include:\n"
            "- allowed_action_space: list[str]\n"
            "- forbidden_action_space: list[{action:str, reason:str}]\n"
            "- contact_and_org_boundaries: object\n"
            "- requires_escalation_actions: list[str]\n"
            "- allowed_action_space MUST be a strict subset of q4_capability_boundary_profile.actionable_space.\n"
            "- Every string in allowed_action_space must be copied verbatim from the Q4 actionable_space input; do not invent or paraphrase actions.\n"
            "- If an action is not present in Q4 actionable_space, it must not appear in allowed_action_space.\n\n"
            f"{render_q4_boundary(snapshot)}\n\n"
            f"Q4 actionable_space source of truth: {actionable_space}\n"
        )

        model_context = {
            "snapshot_version": snapshot.get("snapshot_version"),
            "q4_capability_boundary_profile": q4_profile,
            "contact_policy": snapshot.get("contact_policy"),
            "tenant_scope": snapshot.get("tenant_scope"),
            "agent_trust_policy": snapshot.get("agent_trust_policy"),
            "q3_connected_agents": snapshot.get("q3_connected_agents"),
            "functional_authorization_inputs": functional_authorization_inputs,
        }

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
        if not set(map(str, allowed)).issubset(set(map(str, actionable_space))):
            raise RuntimeError("Q5 authorization violation: allowed_action_space exceeds Q4 actionable_space")
        normalized_permission_boundary = {
            "authorized_actions": list(allowed),
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
                "q5_functional_authorization_inputs": functional_authorization_inputs,
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
