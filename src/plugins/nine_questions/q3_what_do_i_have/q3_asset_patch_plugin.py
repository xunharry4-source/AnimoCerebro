from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from zentex.core.plugin_base import BaseCapabilityPatchPlugin, PluginLifecycleStatus, PluginHealthStatus
from zentex.common.nine_questions_shared import (
    require_model_provider,
    require_transcript_store,
    build_caller_context,
    render_q3_asset_inventory,
    record_model_invoked,
    record_model_completed,
    record_model_failed,
)

logger = logging.getLogger(__name__)


class Q3AssetEnhancementPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Q3: What do I have? (Asset Inventory Enhancement Patch).
    Specialized asset analysis for complex or unknown workspaces.
    Supports concurrent execution with the base Q3 plugin.
    """
    
    plugin_id: str = "q3_asset_enhancement_patch"
    display_name: str = "Q3 Asset Enhancement (Deep Workspace Scan)"
    behavior_key: str = "q3_what_do_i_have"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["logic_drift"]
    revocation_reasons: List[str] = []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized asset inventory logic.
        """
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        trace_id = context.get("trace_id", "q3-asset-patch-trace")
        
        system_prompt = (
            "你现在是 Zentex 外部大脑的资产增强盘点内核。你的任务是基于 Q3 已盘点出的基础资产清单，"
            "进行更深层次的资产‘潜在能力评估’（例如：如果我有这个金融工具，它能进行哪些非标准的衍生交易？）。"
            "你必须输出资产的隐藏属性、可用容量上限及资源依赖图。"
        )
        
        user_prompt = render_q3_asset_inventory({"q3_unified_asset_inventory": context.get("asset_inventory")})
        
        caller_context = build_caller_context(
            invocation_phase="q3_asset_enhancement",
            source_module="q3_asset_patch_plugin",
            question_ref="我有什么(资产增强)",
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
                context={"asset_inventory": context.get("asset_inventory")},
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
            return {"q3_asset_enhancement": result}

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


def build_q3_asset_patch_plugin(
    *,
    plugin_id: str = "q3_asset_enhancement_patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q3AssetEnhancementPatchPlugin:
    return Q3AssetEnhancementPatchPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q3",
        status=status,
    )
