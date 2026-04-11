from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import Field

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext
from zentex.common.nine_questions_shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_human_readable_block,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q1EnhancementPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q1: Where am I? (Domain Enhancement Patch).
    Allows specialized environment deduction (financial, security, codebase).
    Supports concurrent execution with the base Q1 plugin.
    """
    
    plugin_id: str = "q1_enhancement_patch"
    display_name: str = "Q1 Domain Enhancement (Finance/Security)"
    behavior_key: str = "q1_where_am_i"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["logic_drift"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized environment reasoning.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q1-enhancement-trace")
        
        # In a real scenario, this would use specialized prompts for domain knowledge.
        system_prompt = (
            "你现在是 Zentex 外部大脑的环境增强推演内核。你的任务是基于 Q1 的初步环境感官信号，"
            "进行更深层次的领域内涵分析（例如：这是金融核心生产环境还是本地沙箱环境？）。"
            "你必须输出该领域的特有约束及隐匿风险।"
        )
        
        user_prompt = render_human_readable_block(context.get("context_snapshot"), heading="输入信号快照")
        
        caller_context = build_caller_context(
            invocation_phase="q1_enhancement",
            source_module="q1_enhancement_patch_plugin",
            question_ref="我在哪(增强推演)",
            question_driver_refs=context.get("question_driver_refs"),
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=context.get("session_id", "unknown"),
            turn_id=context.get("turn_id", "unknown"),
            trace_id=trace_id,
            source=self.plugin_id,
            payload={"prompt": user_prompt, "system_prompt": system_prompt}
        )

        try:
            result = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={"context_snapshot": context.get("context_snapshot")},
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
            return {"q1_domain_enhancement": result}

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
