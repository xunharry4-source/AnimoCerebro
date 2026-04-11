from __future__ import annotations

from typing import Any, Dict

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.capability_patch_base import BaseCapabilityPatchPlugin
# Decoupled: Inputs come directly from context snapshot


class Q1WhereAmIEnhancementPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Capability enhancement for Q1 (我在哪).
    Focuses on identifying domain-specific semantic tokens (financial, code, security).
    """
    question_ref: str = "我在哪-能力增强补丁"
    source_module: str = "q1_where_am_i_patch"
    invocation_phase: str = "nine_question_q1_patch"
    context_update_key: str = "q1_capability_patch"

    def _get_local_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # Directly extract from the universal context snapshot (provided by the sensory bus)
        snapshot = context.get("context_snapshot") or {}
        return {
            "structure_summary": snapshot.get("structure"),
            "samples_summary": snapshot.get("samples"),
            "environment_event": snapshot.get("environment_event"),
            "physical_host_state": snapshot.get("physical_host_state"),
        }

    def _get_prompt(self) -> str:
        return (
            "You are Zentex. This is a capability enhancement patch for Q1 (我在哪).\n"
            "Analyze the workspace context and output an additive patch highlighting:\n"
            "1) semantic domain tags (finance, dev, security)\n"
            "2) hidden environment risks\n"
            "3) implicit dependencies\n"
            "Return STRICT JSON with keys: patch_summary, patch_updates.\n"
        )


def build_q1_where_am_i_capability_patch_plugin(
    *,
    plugin_id: str = "nine-question-q1-where-am-i-capability-patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q1WhereAmIEnhancementPatchPlugin:
    return Q1WhereAmIEnhancementPatchPlugin(
        plugin_id=plugin_id,
        version="1.1.0",
        feature_code="nine_questions.q1",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        tool_type="nine_question_capability_patch",
        purpose="Additive semantic refinement for Q1.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["patch_summary", "patch_updates"]},
        required_context=["context_snapshot", "transcript_store", "model_provider"],
        trigger_conditions=["inspection"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=False,
        rollback_conditions=["q1_patch_regression"],
        revocation_reasons=[],
        do_not_use_when=["missing_model_provider"],
    )
