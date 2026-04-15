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
# Decoupled: Inputs come from identity constraint and red-line plugins
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


QUESTION_REF = "我即使能做也不该做什么"

logger = logging.getLogger(__name__)


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

        # 2. Prepare Mandatory System Prompt
        system_prompt = (
            "你现在是 Zentex 外部大脑的红线与禁区生成中枢。请严格对比当前系统的『可行动作空间』与底层的『不可绕过约束/历史禁令』。\n"
            "你的任务是：明确指出在当前特定环境下，系统即使物理上能做、权限上被允许，也**绝对不该做**的事情。"
            "你必须返回严格 JSON，顶层键只能是 `forbidden_zone_profile`，禁止输出 `redline_policy_report` 或任何其他顶层键。"
        )

        # 3. Prepare Context for LLM
        model_context = {
            "q4_capability_boundary": context.get("q4_capability_boundary_profile"), # Action space from Q4
            "q5_authorization_boundary": context.get("q5_permission_boundary"),      # Auth space from Q5
            "global_constraints": global_constraints,
            "redline_hints": redline_hints,
            "output_contract": {
                "forbidden_zone_profile": {
                    "absolute_red_lines": ["string"],
                    "performance_tradeoff_bans": ["string"],
                    "prohibited_strategies": ["string"],
                    "contamination_risks": ["string"],
                }
            },
        }
        prompt = (
            f"{system_prompt}\n\n"
            f"{render_q4_boundary(context)}\n\n"
            f"{render_q5_boundary(context)}\n\n"
            f"{render_human_readable_block(global_constraints, heading='全局不可绕过约束')}\n\n"
            f"{render_human_readable_block(redline_hints, heading='场景红线提示')}\n\n"
            "输出契约:\n"
            "{\n"
            '  "forbidden_zone_profile": {\n'
            '    "absolute_red_lines": ["no fabricated runtime state"],\n'
            '    "performance_tradeoff_bans": ["no skipping audit for speed"],\n'
            '    "prohibited_strategies": ["unaudited direct production write"],\n'
            '    "contamination_risks": ["credential leakage into transcript"]\n'
            "  }\n"
            "}\n"
        )

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
            source="plugins.nine_questions.q6_consequences",
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
                source="plugins.nine_questions.q6_consequences",
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

        # 7. Audit Log: Completion
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q6_consequences",
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
