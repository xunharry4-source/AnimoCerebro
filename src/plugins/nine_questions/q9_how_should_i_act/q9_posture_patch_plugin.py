from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import Field

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import PostureSpec
from plugins.nine_questions._shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_human_readable_block,
    render_nine_questions_snapshot,
    render_plugin_catalog,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q9PosturePatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q9: How should I act? (Posture & Style Patch).
    Controls risk appetite, confirmation triggers, and evaluation bias.
    Supports multi-plugin concurrency.
    """

    plugin_id: str = "q9_posture_patch"
    display_name: str = "Q9 Posture Optimization (Control/Rhythm)"
    behavior_key: str = "q9_how_should_i_act"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["unsafe_posture"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized posture deduction.
        Refines the action rhythm and evaluation style.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q9-posture-patch-trace")
        
        # Discover active Posture strategy oracles
        registry = context.get("plugin_registry")
        posture_oracles = []
        if registry:
            active = registry.get_active_plugins()
            posture_oracles = [p.plugin_id for p in active if isinstance(p, PostureSpec)]

        system_prompt = (
            "你现在是 Zentex 外部大脑的行事姿态定调内核。你的任务是决定大脑在执行主路径时的“节奏与确认策略”。\n"
            "根据当前负载、预算与安全红线，动态修正系统的评估风格（如强制转为保守求证）与演化学习焦点。\n"
            "你必须输出节奏建议、关键确认点以及针对不同环境（Dev/Prod）的风险偏好调节。"
        )
        user_prompt = (
            f"{render_nine_questions_snapshot(context.get('nine_questions'))}\n\n"
            f"{render_human_readable_block(context.get('context_snapshot'), heading='全局上下文快照')}\n\n"
            f"{render_plugin_catalog(posture_oracles, heading='姿态策略插件')}"
        )
        
        caller_context = build_caller_context(
            invocation_phase="q9_posture_enhancement",
            source_module="q9_posture_patch_plugin",
            question_ref="应该如何行动(姿态定调)",
            question_driver_refs=context.get("question_driver_refs"),
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=context.get("session_id", "unknown"),
            turn_id=context.get("turn_id", "unknown"),
            trace_id=trace_id,
            source=self.plugin_id,
            payload={"prompt": user_prompt, "posture_oracles": posture_oracles}
        )

        try:
            result = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={
                    "nine_questions": context.get("nine_questions"),
                    "context_snapshot": context.get("context_snapshot"),
                    "posture_oracles": posture_oracles,
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
            return {"q9_posture_enhancement": result}

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


def build_q9_posture_patch_plugin(
    *,
    plugin_id: str = "q9_posture_patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q9PosturePatchPlugin:
    return Q9PosturePatchPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q9",
        status=status,
    )
