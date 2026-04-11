from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import Field

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import ObjectiveSpec
from zentex.common.nine_questions_shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_nine_questions_snapshot,
    render_plugin_catalog,
    render_task_state,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q8ObjectivePatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q8: What should I do now? (Objective & Task Queue Patch).
    Allows specialized objective re-prioritization and unblocking logic.
    Supports multi-plugin concurrency.
    """

    plugin_id: str = "q8_objective_patch"
    display_name: str = "Q8 Objective Optimization (Efficiency/Priority)"
    behavior_key: str = "q8_what_should_i_do_now"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["priority_inversion"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized objective inference.
        Refines the AutonomousTaskQueue.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q8-objective-patch-trace")
        
        # Discover active Objective oracles
        registry = context.get("plugin_registry")
        objective_oracles = []
        if registry:
            active = registry.get_active_plugins()
            objective_oracles = [p.plugin_id for p in active if isinstance(p, ObjectiveSpec)]

        system_prompt = (
            "你现在是 Zentex 外部大脑的终极决策增强内核。你的任务是基于当前的所有认知审计节点（Q1-Q7），"
            "对主目标生成的任务队列进行并发式的‘优先级重新排列’或‘阻塞解除推演’。\n"
            "你必须输出优化后的任务分发链、核心动作参数以及应对阻塞的备选行动建议。"
        )
        user_prompt = (
            f"{render_nine_questions_snapshot(context.get('nine_questions'))}\n\n"
            f"{render_task_state(context.get('task_queue_inference'))}\n\n"
            f"{render_plugin_catalog(objective_oracles, heading='目标策略插件')}"
        )
        
        caller_context = build_caller_context(
            invocation_phase="q8_objective_enhancement",
            source_module="q8_objective_patch_plugin",
            question_ref="我现在应该做什么(决策增强)",
            question_driver_refs=context.get("question_driver_refs"),
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=context.get("session_id", "unknown"),
            turn_id=context.get("turn_id", "unknown"),
            trace_id=trace_id,
            source=self.plugin_id,
            payload={"prompt": user_prompt, "objective_oracles": objective_oracles}
        )

        try:
            result = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={
                    "nine_questions": context.get("nine_questions"),
                    "task_queue_inference": context.get("task_queue_inference"),
                    "objective_oracles": objective_oracles,
                },
                caller_context=caller_context
            )
            
            record_model_completed(
                transcript_store,
                session_id=context.get("session_id", "unknown"),
                turn_id=context.get("turn_id", "unknown"),
                trace_id=trace_id,
                source=self.plugin_id,
                payload={"result": result}
            )
            return {"q8_objective_enhancement": result}

        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=context.get("session_id", "unknown"),
                turn_id=context.get("turn_id", "unknown"),
                trace_id=trace_id,
                source=self.plugin_id,
                payload={"error": str(exc)}
            )
            raise


def build_q8_objective_patch_plugin(
    *,
    plugin_id: str = "q8_objective_patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q8ObjectivePatchPlugin:
    return Q8ObjectivePatchPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q8",
        status=status,
    )
