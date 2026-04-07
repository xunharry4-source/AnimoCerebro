from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import ExecutionPluginSpec
from plugins.nine_questions._shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_plugin_catalog,
    render_q3_asset_inventory,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q4CapabilityEnhancementPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q4: What can I do? (Capability Enhancement Patch).
    Allows specialized capability assessment for specific operation domains.
    Supports multi-plugin concurrency.
    """

    plugin_id: str = "q4_capability_enhancement_patch"
    display_name: str = "Q4 Capability Expansion (DevOps/Code)"
    behavior_key: str = "q4_what_can_i_do"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["capability_drift"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized capability assessment.
        Connects with Execution Domains for physical fact checking.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q4-capability-patch-trace")
        
        # 1. Discover active Execution Domains
        registry = context.get("plugin_registry")
        exec_domains = []
        if registry:
            active = registry.get_active_plugins()
            exec_domains = [p.execution_domain for p in active if isinstance(p, ExecutionPluginSpec)]

        system_prompt = (
            "你现在是 Zentex 外部大脑的能力评估增强内核。任务是基于当前的 Execution Domains，"
            "评估系统在特定领域（如运维故障处理、代码重构）的极致行动上限。\n"
            "你必须输出该场景下的高阶动作方案及资源消耗预估。"
        )
        user_prompt = (
            f"{render_plugin_catalog(exec_domains, heading='执行域目录')}\n\n"
            f"{render_q3_asset_inventory(context)}"
        )
        
        caller_context = build_caller_context(
            invocation_phase="q4_capability_enhancement",
            source_module="q4_capability_patch_plugin",
            question_ref="我能做什么(能力增强)",
            question_driver_refs=context.get("question_driver_refs"),
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=context.get("session_id", "unknown"),
            turn_id=context.get("turn_id", "unknown"),
            trace_id=trace_id,
            source=self.plugin_id,
            payload={"prompt": user_prompt, "system_prompt": system_prompt, "exec_domains": exec_domains}
        )

        try:
            result = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={
                    "q3_unified_asset_inventory": context.get("q3_unified_asset_inventory"),
                    "exec_domains": exec_domains,
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
            return {"q4_capability_enhancement": result}

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


def build_q4_capability_patch_plugin(
    *,
    plugin_id: str = "q4_capability_enhancement_patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q4CapabilityEnhancementPatchPlugin:
    return Q4CapabilityEnhancementPatchPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q4",
        status=status,
    )
