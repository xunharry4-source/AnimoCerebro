import logging
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.core.models import LogicalCognitiveToolSpec
from zentex.core.plugin_base import PluginLifecycleStatus, PluginHealthStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult

from plugins.nine_questions.q8_what_should_i_do_now.models import (
    Q8InferenceResult,
)
# Decoupled: Inputs come from objective strategy plugins
from zentex.core.plugin_family import ObjectiveSpec

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
    render_task_state,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)


class WhatShouldIDoNowPlugin(LogicalCognitiveToolSpec):
    """
    [LLM MANDATORY] Q8 Phase Plugin.
    Synopsizes Q1-Q7 to generate the current focus and task queue.
    The core decision hub for the Zentex G31A Autonomous Controller.
    """
    plugin_id: str = "nine_question_q8_decision"
    display_name: str = "Q8: What should I do now? (Decision & Tasking)"
    behavior_key: str = "q8_final_decision"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["unhandled_llm_failure"]
    revocation_reasons: List[str] = []
    tool_type: str = "nine_question"
    purpose: str = "Synthesize current primary objective and task queue under Q1-Q7 constraints."
    input_schema: Dict[str, Any] = {"type": "object"}
    output_schema: Dict[str, Any] = {"type": "object"}
    required_context: List[str] = ["nine_questions", "persistent_task_state", "plugin_registry", "transcript_store", "model_provider"]
    trigger_conditions: List[str] = ["inspection", "always"]
    do_not_use_when: List[str] = ["missing_model_provider"]
    read_only: bool = True
    side_effect_free: bool = True
    is_default_version: bool = True
    is_official_release: bool = True

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize current primary objective and tasks.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        
        # 1. G-series Objective Strategy Oracle Discovery
        try:
             registry = context.get("plugin_registry")
             if not registry:
                 raise RuntimeError("Plugin Registry missing from context.")
             
             # Locate active objective oracles
             active_plugins = registry.get_active_plugins()
             obj_oracles = [p.plugin_id for p in active_plugins if isinstance(p, ObjectiveSpec)]
             
        except Exception as exc:
             logger.error(f"Objective Discovery Failure: {exc}")
             raise RuntimeError(f"Q8 Decision Path Break: {exc}") from exc

        # 3. Build synthesis prompt
        system_prompt = (
            "你现在是 Zentex 外部大脑的主目标生成与任务排序中枢。请严格审查传入的 Q1-Q7 约束条件。\n"
            "你的任务是：在绝对不违背 Q5（权限）和 Q6（红线）的前提下，基于 Q3/Q4 的真实能力，"
            "推断现在最应该推进的主目标是什么？当前阶段的具体任务是什么？"
        )
        objective_catalog = render_plugin_catalog(obj_oracles, heading="可用目标策略插件")
        nine_questions_summary = render_nine_questions_snapshot(context.get("nine_questions"))
        task_state_summary = render_task_state(context.get("persistent_task_state"))

        user_prompt = f"""
### 聚合状态快照 (Cognitive Snapshot Q1-Q7)
{nine_questions_summary}

### 任务状态机快照
{task_state_summary}

### 可用目标策略插件
{objective_catalog}

### 任务
综合判断，输出严格 JSON。
顶层只能包含：
- `objective_profile`
- `task_queue`

禁止输出：
- `ObjectiveProfile`
- `AutonomousTaskQueue`
- `ConstraintCompliance`
- 任何其他额外顶层键

`objective_profile` 必须包含：
- `current_primary_objective`: str
- `current_phase_tasks`: list[str]
- `priority_order`: list[str]

`task_queue` 必须包含：
- `next_self_tasks`: list[object]
- `blocked_self_tasks`: list[object]
- `proactive_actions`: list[object]

输出示例：
{{
  "objective_profile": {{
    "current_primary_objective": "verify live nine-question chain end-to-end",
    "current_phase_tasks": ["inspect current failure point", "repair runtime contract drift"],
    "priority_order": ["repair contract drift", "rerun live validation"]
  }},
  "task_queue": {{
    "next_self_tasks": [{{"task_id": "repair-q8", "title": "repair Q8 contract drift"}}],
    "blocked_self_tasks": [{{"task_id": "verify-ui", "reason": "waiting for successful Q1-Q9 run"}}],
    "proactive_actions": [{{"task_id": "capture-live-stack", "title": "capture next live stack if rerun fails"}}]
  }}
}}

核心关注点：物理任务优先级是否匹配活跃策略插件逻辑？
"""

        trace_id = str(context.get("trace_id") or f"q8-decision:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")

        # 4. Invoke LLM with strict traceability
        caller_context = build_caller_context(
            invocation_phase="nine_question_q8_decision",
            source_module="q8_what_should_i_do_now_plugin",
            question_ref="我现在应该做什么",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q8_what_should_i_do_now",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": "我现在应该做什么",
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "context": {
                    "nine_questions": context.get('nine_questions'),
                    "persistent_task_state": context.get("persistent_task_state"),
                    "active_objectives": obj_oracles,
                },
            },
        )

        try:
            started = perf_counter()
            result_raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={
                    "nine_questions": context.get("nine_questions"),
                    "persistent_task_state": context.get("persistent_task_state"),
                    "active_objectives": obj_oracles,
                },
                caller_context=caller_context
            )
            elapsed_ms = int((perf_counter() - started) * 1000)

            # 5. Validate & Return
            inference = Q8InferenceResult.model_validate(result_raw)
            objective = inference.objective_profile
            queue = inference.task_queue

            record_model_completed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q8_what_should_i_do_now",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我现在应该做什么",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": inference.model_dump(mode="json"),
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                    "elapsed_ms": elapsed_ms,
                },
            )

            # Return as a flattened dictionary for the state machine
            return {
                "objective": objective.model_dump(mode="json"),
                "task_queue": queue.model_dump(mode="json")
            }

        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q8_what_should_i_do_now",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我现在应该做什么",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            logger.error(f"Q8 LLM Failure: {exc}")
            raise RuntimeError(f"[LLM MANDATORY] Q8 synthesis failed: {exc}") from exc

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        result = self.execute(dict(context))
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Synthesized objective and task queue (Q8)",
            proposals=[
                {
                    "kind": "nine_question_q8_decision",
                    "result": result,
                }
            ],
            context_updates={
                "q8_objective_and_queue": result,
                "q8_objective_profile": result.get("objective"),
                "q8_task_queue": result.get("task_queue"),
            },
            confidence=0.8,
        )


def build_q8_what_should_i_do_now_plugin(
    *,
    plugin_id: str = "nine_question_q8_decision",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> WhatShouldIDoNowPlugin:
    return WhatShouldIDoNowPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q8",
        status=status,
    )
