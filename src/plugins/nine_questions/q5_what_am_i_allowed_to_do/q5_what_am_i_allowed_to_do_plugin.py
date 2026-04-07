from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.core.models import LogicalCognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore

QUESTION_REF = "我被允许做什么"


from plugins.nine_questions._shared import (
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

logger = logging.getLogger(__name__)


class Q5WhatAmIAllowedToDoPlugin(LogicalCognitiveToolSpec):
    """
    Zentex Cognitive Kernel Phase 5: 我被允许做什么 (Q5: Authorization & Compliance).

    [LLM MANDATORY]: Guarantees that authorization is a semantic, non-bypassable deduction.
    """

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        snapshot = context.get("context_snapshot", {}) or {}
        q4_profile = snapshot.get("q4_capability_boundary_profile", {}) or {}
        actionable_space = list(q4_profile.get("actionable_space", []) or [])

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

        profile = raw.get("authorization_boundary_profile") if isinstance(raw, dict) else None
        if not isinstance(profile, dict):
            raise ValueError("Invalid Q5 output: missing authorization_boundary_profile")
        allowed = profile.get("allowed_action_space")
        if not isinstance(allowed, list):
            raise ValueError("Invalid Q5 output: allowed_action_space must be a list")
        if not set(map(str, allowed)).issubset(set(map(str, actionable_space))):
            raise RuntimeError("Q5 authorization violation: allowed_action_space exceeds Q4 actionable_space")

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
            },
            confidence=0.9,
        )


def build_q5_what_am_i_allowed_to_do_plugin(
    *,
    plugin_id: str = "nine-question-q5-what-am-i-allowed-to-do",
    version: str = "2.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q5WhatAmIAllowedToDoPlugin:
    return Q5WhatAmIAllowedToDoPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q5",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["authorization_inference_regression"],
        revocation_reasons=[],
        tool_type="nine_question",
        purpose="Semantic authorization boundary & compliance check (Q5).",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["permission_boundary", "compliance_checklist"]},
        required_context=["context_snapshot", "transcript_store"],
        trigger_conditions=["inspection"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=True,
        do_not_use_when=["missing_model_provider"],
    )
