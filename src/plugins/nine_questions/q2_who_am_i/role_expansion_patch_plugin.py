from __future__ import annotations

from typing import Any, Dict

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from plugins.nine_questions.capability_patch_base import BaseCapabilityPatchPlugin


class Q2RoleExpansionPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Capability enhancement for Q2 (我是谁).
    Focuses on expanding the identity model with hidden principles and long-term mission facets.
    """
    question_ref: str = "我是谁-角色扩展补丁"
    source_module: str = "q2_who_am_i_patch"
    invocation_phase: str = "nine_question_q2_patch"

    def _get_local_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # Simple extraction for Q2
        snapshot = context.get("context_snapshot", {})
        return {
            "identity_hints": snapshot.get("identity_hints", {}),
            "environment_type": snapshot.get("environment_type", "unknown"),
        }

    def _get_prompt(self) -> str:
        return (
            "You are Zentex. This is a capability enhancement patch for Q2 (我是谁).\n"
            "Analyze the identity hints and environment to output an additive patch highlighting:\n"
            "1) secondary identity roles\n"
            "2) implicit cognitive principles (e.g. strict auditing, fail-closed)\n"
            "3) mission boundary refinements\n"
            "Return STRICT JSON with keys: patch_summary, patch_updates.\n"
        )


def build_q2_role_expansion_patch_plugin(
    *,
    plugin_id: str = "nine-question-q2-role-expansion-patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q2RoleExpansionPatchPlugin:
    return Q2RoleExpansionPatchPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code="nine_questions.q2",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        tool_type="nine_question_capability_patch",
        purpose="Additive role refinement for Q2.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["patch_summary", "patch_updates"]},
        required_context=["context_snapshot", "transcript_store", "model_provider"],
        trigger_conditions=["re-identification"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=False,
        rollback_conditions=["q2_patch_regression"],
        revocation_reasons=[],
        do_not_use_when=["missing_model_provider"],
    )
