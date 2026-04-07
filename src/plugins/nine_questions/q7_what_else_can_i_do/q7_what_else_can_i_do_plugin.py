import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.core.models import LogicalCognitiveToolSpec
from zentex.core.plugin_base import PluginLifecycleStatus, PluginHealthStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult

from plugins.nine_questions.q7_what_else_can_i_do.models import AlternativeStrategyProfile, Q7InferenceResult
# Decoupled: Inputs come from alternative strategy plugins
from zentex.core.plugin_family import AlternativeSpec

logger = logging.getLogger(__name__)


from plugins.nine_questions._shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_nine_questions_snapshot,
    render_plugin_catalog,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)


class WhatElseCanIDoPlugin(LogicalCognitiveToolSpec):
    """
    [LLM MANDATORY] Q7 Phase Plugin.
    Generates fallback and degradation strategies based on Q3-Q6 constraints.
    """
    plugin_id: str = "nine_question_q7_alternatives"
    display_name: str = "Q7: What else can I do? (Alternatives & Fallbacks)"
    behavior_key: str = "q7_alternative_strategy"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["unhandled_llm_failure"]
    revocation_reasons: List[str] = []
    tool_type: str = "nine_question"
    purpose: str = "Generate fallback strategies and safe degradations when the primary path is blocked."
    input_schema: Dict[str, Any] = {"type": "object"}
    output_schema: Dict[str, Any] = {"type": "object"}
    required_context: List[str] = ["nine_questions", "plugin_registry", "transcript_store", "model_provider"]
    trigger_conditions: List[str] = ["inspection", "fallback_required", "always"]
    do_not_use_when: List[str] = ["missing_model_provider"]
    read_only: bool = True
    side_effect_free: bool = True
    is_default_version: bool = True
    is_official_release: bool = True

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize fallback strategies via LLM.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        
        # 1. G-series Alternative Strategy Oracle Discovery
        try:
             registry = context.get("plugin_registry")
             if not registry:
                 raise RuntimeError("Plugin Registry missing from context.")
             
             # Locate active alternative strategies
             active_plugins = registry.get_active_plugins()
             alt_oracles = [p.plugin_id for p in active_plugins if isinstance(p, AlternativeSpec)]
             
        except Exception as exc:
             logger.error(f"Alternative Discovery Failure: {exc}")
             raise RuntimeError(f"Q7 Reliability Path Break: {exc}") from exc

        # 3. Build Prompt with deadlocks
        system_prompt = (
            "你现在是 Zentex 外部大脑的备选战略与降级规划中枢。请严格基于传入的能力上限（Q4）、"
            "授权边界（Q5）、底线禁区（Q6）以及历史失败经验，假设当前系统的‘最优主路径’已经受阻或不可行。"
            "你的任务是：由于主路径受限，系统必须生成合规的替代动作或求助方式。"
        )
        alternative_catalog = render_plugin_catalog(alt_oracles, heading="可用备选策略插件")
        nine_questions_summary = render_nine_questions_snapshot(context.get("nine_questions"))

        user_prompt = f"""
### 前置认知事实 (Constraints from Q3-Q6)
{nine_questions_summary}

### 可用备选策略插件
{alternative_catalog}

### 任务
生成严格 JSON。
顶层只能是 `alternative_strategy_profile`。
禁止输出 `Q7InferenceResult` 作为顶层键，禁止再包一层对象。
`alternative_strategy_profile` 必须且只能包含：
- `fallback_plans`: list[str]
- `degradation_strategies`: list[str]
- `collaboration_switches`: list[str]
- `exploratory_actions`: list[str]

输出示例：
{{
  "alternative_strategy_profile": {{
    "fallback_plans": ["switch to read-only audit mode"],
    "degradation_strategies": ["reduce scope to evidence collection only"],
    "collaboration_switches": ["request human review for blocked write path"],
    "exploratory_actions": ["inspect latest transcript for failure cause"]
  }}
}}

核心关注点：由于主路径被封锁，物理降级方案是否满足活跃策略插件逻辑？
"""

        trace_id = str(context.get("trace_id") or f"q7-alternatives:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")

        # 4. Invoke LLM with strict traceability
        caller_context = build_caller_context(
            invocation_phase="nine_question_q7_alternatives",
            source_module="q7_what_else_can_i_do_plugin",
            question_ref="我还可以做什么",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q7_what_else_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": "我还可以做什么",
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "context": {
                    "nine_questions": context.get('nine_questions'),
                    "active_alternatives": alt_oracles,
                },
            },
        )

        try:
            result_raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={
                    "nine_questions": context.get("nine_questions"),
                    "active_alternatives": alt_oracles,
                },
                caller_context=caller_context
            )

            # 5. Validate & Return
            inference = Q7InferenceResult.model_validate(result_raw)
            profile = inference.alternative_strategy_profile

            record_model_completed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q7_what_else_can_i_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我还可以做什么",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": profile.model_dump(mode="json"),
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                },
            )

            return profile.model_dump(mode="json")

        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q7_what_else_can_i_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我还可以做什么",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            logger.error(f"Q7 LLM Failure: {exc}")
            raise RuntimeError(f"[LLM MANDATORY] Q7 synthesis failed: {exc}") from exc

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        result = self.execute(dict(context))
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Generated alternative strategies and fallback plans (Q7)",
            proposals=[
                {
                    "kind": "nine_question_q7_alternatives",
                    "result": result,
                }
            ],
            context_updates={
                "q7_alternative_strategy_profile": result,
            },
            confidence=0.8,
        )


def build_q7_what_else_can_i_do_plugin(
    *,
    plugin_id: str = "nine_question_q7_alternatives",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> WhatElseCanIDoPlugin:
    return WhatElseCanIDoPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q7",
        status=status,
    )
