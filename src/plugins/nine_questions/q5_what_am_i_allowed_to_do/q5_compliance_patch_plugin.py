from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import Field

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import CompliancePluginSpec, TrustPolicySpec
from plugins.nine_questions._shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_human_readable_block,
    render_q4_boundary,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q5CompliancePatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q5: What am I allowed to do? (Compliance Patch).
    Performs 'subtractive cropping' on the action space based on specific compliance rules.
    Integrates with Contact & Trust Policy plugins.
    """
    
    plugin_id: str = "q5_compliance_patch"
    display_name: str = "Q5 Compliance Audit (Financial/Privacy)"
    behavior_key: str = "q5_what_am_i_allowed_to_do"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["logic_drift"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized compliance audit.
        Reads Contact Whitelists and Agent Trust Scopes.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q5-compliance-patch-trace")
        
        # 1. Integrate Trust Policies
        registry = context.get("plugin_registry")
        whitelists = []
        trust_policies = []
        if registry:
            active = registry.get_active_plugins()
            whitelists = [p.get_whitelist() for p in active if isinstance(p, TrustPolicySpec)]
            trust_policies = [p.plugin_id for p in active if isinstance(p, TrustPolicySpec)]

        system_prompt = (
            "你现在是 Zentex 外部大脑的合规安检内核。你的任务是基于当前的‘联系策略白名单’与‘Agent 授信策略’，"
            "对 Q4 输出的可行动作集进行并发式的‘减法裁剪’。\n"
            "你必须输出该场景下的授权裁剪结果、任何越权封禁记录以及合规检查清单।"
        )
        user_prompt = (
            f"{render_human_readable_block(whitelists, heading='联系域白名单')}\n\n"
            f"{render_human_readable_block(trust_policies, heading='授信策略插件')}\n\n"
            f"{render_q4_boundary(context)}"
        )
        
        caller_context = build_caller_context(
            invocation_phase="q5_compliance_patch",
            source_module="q5_compliance_patch_plugin",
            question_ref="我被允许做什么(合规增强)",
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
                    "whitelists": whitelists,
                    "trust_policies": trust_policies,
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
            return {"q5_compliance_patch": result}

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


def build_q5_compliance_patch_plugin(
    *,
    plugin_id: str = "q5_compliance_patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q5CompliancePatchPlugin:
    return Q5CompliancePatchPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q5",
        status=status,
    )
