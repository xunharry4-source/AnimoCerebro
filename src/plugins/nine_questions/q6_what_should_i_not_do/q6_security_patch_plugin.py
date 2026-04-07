from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import Field

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import RedlinePluginSpec, IdentityPackageSpec
from plugins.nine_questions._shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_human_readable_block,
    render_q4_boundary,
    render_q5_boundary,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q6SecurityRedlinePatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q6: What should I not do? (Security Red-line Patch).
    Generates scene-specific red-lines that cannot be compromised.
    Integrates with Identity Constraint Packs (G10).
    """

    plugin_id: str = "q6_security_redline_patch"
    display_name: str = "Q6 Security Defense (Red-line Enhancement)"
    behavior_key: str = "q6_what_should_i_not_do"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["security_leak"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized red-line generation.
        Integrates with Identity Constraint Packs for absolute no-go areas.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q6-security-patch-trace")
        
        # 1. Integrate Identity Constraint Packs (G10)
        registry = context.get("plugin_registry")
        global_constraints = []
        if registry:
            active = registry.get_active_plugins()
            global_constraints = [p.get_payload() for p in active if isinstance(p, IdentityPackageSpec) and p.pack_type == "constraint_pack"]

        system_prompt = (
            "你现在是 Zentex 外部大脑的安全防线内核。你的任务是基于当前的‘身份内核禁令’与‘场景风险’，"
            "为当前动作推演生成物理级的安全红线与禁区。\n"
            "你必须输出该场景下绝对禁止的操作、不能妥协的底线准则以及防御性策略提示。"
        )
        user_prompt = (
            f"{render_human_readable_block(global_constraints, heading='底层不可绕过约束')}\n\n"
            f"{render_q4_boundary(context)}\n\n"
            f"{render_q5_boundary(context)}"
        )
        
        caller_context = build_caller_context(
            invocation_phase="q6_security_redline_patch",
            source_module="q6_security_patch_plugin",
            question_ref="即使能做也不该做什么(防线增强)",
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
                context={
                    "q4_inference_result": context.get("q4_inference_result"),
                    "q5_inference_result": context.get("q5_inference_result"),
                    "global_constraints": global_constraints,
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
            return {"q6_security_redline_patch": result}

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


def build_q6_security_patch_plugin(
    *,
    plugin_id: str = "q6_security_redline_patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q6SecurityRedlinePatchPlugin:
    return Q6SecurityRedlinePatchPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q6",
        status=status,
    )
