from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import Field

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext
from plugins.nine_questions._shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_identity_kernel,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q2RoleExpansionPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q2: Who am I? (Role Expansion Patch).
    Allows for dynamic role derivation and identity refinement across different domains.
    Supports concurrent execution with the base Q2 plugin.
    """
    
    plugin_id: str = "q2_role_expansion_patch"
    display_name: str = "Q2 Role Expansion (Dynamic Personality)"
    behavior_key: str = "q2_who_am_i"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["logic_drift"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized role derivation logic.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q2-expansion-trace")
        
        system_prompt = (
            "你现在是 Zentex 外部大脑的角色扩展示演内核。你的任务是基于 Q2 的身份推断初步角色数据，"
            "进行更深层次的‘跨场景角色定义’（例如：如果场景从本地开发切换到远程生产，我的身份特质应如何偏移？）。"
            "你必须输出系统在这种特定语境下应采取的角色偏移量、语气偏好以及主观执行倾向।"
        )
        
        user_prompt = render_identity_kernel(context)
        
        caller_context = build_caller_context(
            invocation_phase="q2_expansion",
            source_module="q2_role_expansion_patch_plugin",
            question_ref="我是谁(角色扩展)",
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
                context={"identity_kernel": context.get("identity_kernel") or context.get("identity_kernel_snapshot")},
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
            return {"q2_role_expansion": result}

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
