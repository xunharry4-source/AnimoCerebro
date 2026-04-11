from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import AlternativeSpec
from zentex.common.nine_questions_shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_plugin_catalog,
    render_q4_boundary,
    render_q6_redlines,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q7AlternativeEnhancementPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q7: What else can I do? (Alternative & Downgrade Patch).
    Allows specialized alternative maneuvers for specific failure domains.
    Supports multi-plugin concurrency.
    """

    plugin_id: str = "q7_alternative_enhancement_patch"
    display_name: str = "Q7 Alternative Expansion (Reliability/Backup)"
    behavior_key: str = "q7_what_else_can_i_do"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["downgrade_loop"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized alternative deduction.
        Integrates with AlternativeSpec oracles.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q7-alternative-patch-trace")
        
        # Discover active Alternative strategy oracles
        registry = context.get("plugin_registry")
        alt_oracles = []
        if registry:
            active = registry.get_active_plugins()
            alt_oracles = [p.plugin_id for p in active if isinstance(p, AlternativeSpec)]

        system_prompt = (
            "你现在是 Zentex 外部大脑的协作降级与备选方案增强内核。你的任务是当主路径受阻时，"
            "基于当前的 Alternative Oracles，推展更加极致、安全的降级动作或协作切换方案。\n"
            "你必须输出该场景下的协作转换细节、降级代价评估以及任何潜在的二次阻塞风险。"
        )
        user_prompt = (
            f"{render_plugin_catalog(alt_oracles, heading='备选策略插件')}\n\n"
            f"{render_q6_redlines(context)}\n\n"
            f"{render_q4_boundary(context)}"
        )
        
        caller_context = build_caller_context(
            invocation_phase="q7_alternative_enhancement",
            source_module="q7_alternative_patch_plugin",
            question_ref="还可以做什么(降级增强)",
            question_driver_refs=context.get("question_driver_refs"),
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=context.get("session_id", "unknown"),
            turn_id=context.get("turn_id", "unknown"),
            trace_id=trace_id,
            source=self.plugin_id,
            payload={"prompt": user_prompt, "alt_oracles": alt_oracles}
        )

        try:
            result = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={
                    "q6_forbidden_zone_profile": context.get("q6_forbidden_zone_profile"),
                    "q4_capability_boundary_profile": context.get("q4_capability_boundary_profile"),
                    "alt_oracles": alt_oracles,
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
            return {"q7_alternative_enhancement": result}

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


def build_q7_alternative_patch_plugin(
    *,
    plugin_id: str = "q7_alternative_enhancement_patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q7AlternativeEnhancementPatchPlugin:
    return Q7AlternativeEnhancementPatchPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q7",
        status=status,
    )
