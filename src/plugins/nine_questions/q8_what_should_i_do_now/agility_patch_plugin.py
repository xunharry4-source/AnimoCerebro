from __future__ import annotations

from typing import Any, Dict

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from plugins.nine_questions.capability_patch_base import BaseCapabilityPatchPlugin


class Q8AgilityPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Capability enhancement for Q8 (我是否需要重规划).
    Focuses on identifying plan drift and emergent task adaptation needs.
    """
    question_ref: str = "我是否需要重规划-敏捷规划补丁"
    source_module: str = "q8_agility_patch"
    invocation_phase: str = "nine_question_q8_patch"

    def _get_local_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = context.get("context_snapshot", {})
        return {
            "current_mission": snapshot.get("q2_mission_boundary", {}),
            "completed_subtasks": snapshot.get("completed_subtasks", []),
            "pending_subtasks": snapshot.get("pending_subtasks", []),
        }

    def _get_prompt(self) -> str:
        return (
            "You are Zentex. This is a capability enhancement patch for Q8 (重规划分析).\n"
            "Analyze the mission and subtasks to output an additive patch for:\n"
            "1) plan drift detection (actual vs expected progress)\n"
            "2) emergent dependency conflicts\n"
            "3) dynamic task priority adjustments\n"
            "Return STRICT JSON with keys: patch_summary, patch_updates.\n"
        )


def build_q8_agility_patch_plugin(
    *,
    plugin_id: str = "nine-question-q8-agility-patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q8AgilityPatchPlugin:
    return Q8AgilityPatchPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code="nine_questions.q8",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        tool_type="nine_question_capability_patch",
        purpose="Additive agility refinement for Q8.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["patch_summary", "patch_updates"]},
        required_context=["context_snapshot", "transcript_store", "model_provider"],
        trigger_conditions=["re-planning"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=False,
        rollback_conditions=["q8_patch_regression"],
        revocation_reasons=[],
        do_not_use_when=["missing_model_provider"],
    )
