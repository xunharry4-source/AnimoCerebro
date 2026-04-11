from __future__ import annotations

from typing import Any, Dict

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.capability_patch_base import BaseCapabilityPatchPlugin


class Q3InventoryAuditPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Capability enhancement for Q3 (我有什么).
    Focuses on auditing the inventory for stale or untrusted assets.
    """
    question_ref = "我有什么-资产审计补丁"
    source_module = "q3_inventory_audit_patch"
    invocation_phase = "nine_question_q3_patch"

    def _get_local_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = context.get("context_snapshot", {})
        return {
            "workspace_assets": snapshot.get("workspace_assets", {}),
            "connected_agents": snapshot.get("connected_agents", []),
            "active_tools": snapshot.get("active_tools", {}),
        }

    def _get_prompt(self) -> str:
        return (
            "You are Zentex. This is a capability enhancement patch for Q3 (我有什么).\n"
            "Audit the asset inventory and output an additive patch for:\n"
            "1) potential trust conflicts\n"
            "2) stale resource pointers\n"
            "3) implicit tool capabilities not explicitly listed\n"
            "Return STRICT JSON with keys: patch_summary, patch_updates.\n"
        )


def build_q3_inventory_audit_patch_plugin(
    *,
    plugin_id: str = "nine-question-q3-inventory-audit-patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q3InventoryAuditPatchPlugin:
    return Q3InventoryAuditPatchPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code="nine_questions.q3",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        tool_type="nine_question_capability_patch",
        purpose="Additive audit refinement for Q3.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["patch_summary", "patch_updates"]},
        required_context=["context_snapshot", "transcript_store", "model_provider"],
        trigger_conditions=["audit"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=False,
        rollback_conditions=["q3_patch_regression"],
        revocation_reasons=[],
        do_not_use_when=["missing_model_provider"],
    )
