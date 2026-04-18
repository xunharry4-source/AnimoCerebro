from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q6
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q6_what_should_i_not_do.models import Q6InferenceResult
from plugins.nine_questions.q6_what_should_i_not_do.llm_prompt import build_q6_llm_request
# Decoupled: Inputs come from identity constraint and red-line plugins
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


QUESTION_REF = "我即使能做也不该做什么"

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


def _normalize_redline_inputs(raw_inputs: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if isinstance(item, dict):
            normalized.append(dict(item))
        elif isinstance(item, list):
            normalized.append({"items": [str(entry).strip() for entry in item if str(entry).strip()]})
    return normalized


def _derive_forbidden_zone_baseline(
    snapshot: dict[str, Any],
    global_constraints: list[dict[str, Any]],
    redline_hints: list[dict[str, Any]],
) -> dict[str, list[str]]:
    q4_profile = snapshot.get("q4_capability_boundary_profile")
    q4_profile = q4_profile if isinstance(q4_profile, dict) else {}
    q5_profile = snapshot.get("q5_authorization_boundary_profile")
    q5_profile = q5_profile if isinstance(q5_profile, dict) else {}
    q5_permission_boundary = snapshot.get("q5_permission_boundary")
    q5_permission_boundary = q5_permission_boundary if isinstance(q5_permission_boundary, dict) else {}

    absolute_red_lines: list[str] = []
    performance_tradeoff_bans: list[str] = []
    prohibited_strategies: list[str] = []
    contamination_risks: list[str] = []

    for item in global_constraints:
        constraints = _coerce_string_list(item.get("non_bypassable_constraints"))
        absolute_red_lines.extend(constraints)
        contamination_risks.extend(_coerce_string_list(item.get("contamination_risks")))

    for item in redline_hints:
        absolute_red_lines.extend(_coerce_string_list(item.get("absolute_red_lines")))
        performance_tradeoff_bans.extend(_coerce_string_list(item.get("performance_tradeoff_bans")))
        prohibited_strategies.extend(_coerce_string_list(item.get("prohibited_strategies")))
        contamination_risks.extend(_coerce_string_list(item.get("contamination_risks")))
        contamination_risks.extend(_coerce_string_list(item.get("forbidden_actions")))
        contamination_risks.extend(_coerce_string_list(item.get("items")))

    forbidden_actions = q5_profile.get("forbidden_action_space")
    if isinstance(forbidden_actions, list):
        for item in forbidden_actions:
            if isinstance(item, dict):
                action = _normalize_text(item.get("action"))
                reason = _normalize_text(item.get("reason"))
                if action and reason:
                    prohibited_strategies.append(f"{action}: {reason}")
                elif action:
                    prohibited_strategies.append(action)

    escalation_actions = _coerce_string_list(q5_profile.get("requires_escalation_actions"))
    if escalation_actions:
        performance_tradeoff_bans.append("no bypassing escalation-required actions")
        prohibited_strategies.extend(
            [f"execute without escalation: {action}" for action in escalation_actions]
        )

    unauthorized_actions = _coerce_string_list(q5_permission_boundary.get("unauthorized_actions"))
    prohibited_strategies.extend(unauthorized_actions)

    actionable_space = _coerce_string_list(q4_profile.get("actionable_space"))
    if not actionable_space:
        absolute_red_lines.append("no action without validated actionable_space")

    permission_profile = snapshot.get("q4_permission_profile")
    permission_profile = permission_profile if isinstance(permission_profile, dict) else {}
    if permission_profile.get("is_read_only") is True:
        performance_tradeoff_bans.append("no write-like actions in read-only mode")

    absolute_red_lines = list(dict.fromkeys(item for item in absolute_red_lines if _normalize_text(item)))
    performance_tradeoff_bans = list(dict.fromkeys(item for item in performance_tradeoff_bans if _normalize_text(item)))
    prohibited_strategies = list(dict.fromkeys(item for item in prohibited_strategies if _normalize_text(item)))
    contamination_risks = list(dict.fromkeys(item for item in contamination_risks if _normalize_text(item)))

    return {
        "absolute_red_lines": absolute_red_lines,
        "performance_tradeoff_bans": performance_tradeoff_bans,
        "prohibited_strategies": prohibited_strategies,
        "contamination_risks": contamination_risks,
    }


def _merge_with_forbidden_baseline(inferred: list[str], baseline: list[str]) -> list[str]:
    return list(dict.fromkeys(_coerce_string_list(inferred) + _coerce_string_list(baseline)))


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
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
        snapshot = context.get("context_snapshot", {}) or {}
        
        global_constraints: list[dict[str, Any]] = []
        redline_hints: list[list[dict[str, Any]] | dict[str, Any]] = []
        plugin_service = context.get("plugin_service")
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
                    if item.get("status") != "done":
                        continue
                    result = item.get("result")
                    if isinstance(result, dict) and "non_bypassable_constraints" in result:
                        global_constraints.append(result)
                    elif isinstance(result, dict) and ("zone" in result or "forbidden_actions" in result):
                        redline_hints.append(result)
                    elif isinstance(result, list):
                        redline_hints.append(result)
            except Exception as exc:
                logger.error(f"Red-line Discovery Failure: {exc}")
                raise RuntimeError(f"Q6 Moral Defense Break: {exc}") from exc
        normalized_global_constraints = _normalize_redline_inputs(global_constraints)
        normalized_redline_hints = _normalize_redline_inputs(redline_hints)
        forbidden_zone_baseline = _derive_forbidden_zone_baseline(
            snapshot,
            normalized_global_constraints,
            normalized_redline_hints,
        )

        llm_request = build_q6_llm_request(
            normalized_global_constraints=normalized_global_constraints,
            normalized_redline_hints=normalized_redline_hints,
            forbidden_zone_baseline=forbidden_zone_baseline,
            rendered_q4_boundary=render_q4_boundary(snapshot),
            rendered_q5_boundary=render_q5_boundary(snapshot),
            rendered_global_constraints=render_human_readable_block(normalized_global_constraints, heading="全局不可绕过约束"),
            rendered_redline_hints=render_human_readable_block(normalized_redline_hints, heading="场景红线提示"),
            rendered_forbidden_baseline=render_human_readable_block(forbidden_zone_baseline, heading="禁区基线"),
            q4_capability_boundary=snapshot.get("q4_capability_boundary_profile"),
            q5_authorization_boundary=snapshot.get("q5_permission_boundary"),
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
            # Fail-Closed: Strictly raise fatal exception.
            raise RuntimeError(f"Q6 Forbidden Zone Inference Failed: {str(exc)}") from exc

        # 6. Validate & Parse (Pydantic v2)
        inference = Q6InferenceResult.model_validate(raw)
        profile = inference.forbidden_zone_profile
        profile.absolute_red_lines = _merge_with_forbidden_baseline(
            profile.absolute_red_lines,
            forbidden_zone_baseline.get("absolute_red_lines", []),
        )
        profile.performance_tradeoff_bans = _merge_with_forbidden_baseline(
            profile.performance_tradeoff_bans,
            forbidden_zone_baseline.get("performance_tradeoff_bans", []),
        )
        profile.prohibited_strategies = _merge_with_forbidden_baseline(
            profile.prohibited_strategies,
            forbidden_zone_baseline.get("prohibited_strategies", []),
        )
        profile.contamination_risks = _merge_with_forbidden_baseline(
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
