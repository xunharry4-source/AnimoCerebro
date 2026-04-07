from __future__ import annotations

from typing import Any, Dict

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from plugins.nine_questions.capability_patch_base import BaseCapabilityPatchPlugin


class Q7GateConfirmationPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Capability enhancement for Q7 (我是否需要确认).
    Focuses on identifying low-latency/high-stakes trigger points.
    """
    question_ref: str = "我是否需要确认-门控确认补丁"
    source_module: str = "q7_gate_patch"
    invocation_phase: str = "nine_question_q7_patch"

    def _get_local_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = context.get("context_snapshot", {})
        return {
            "interaction_mind": snapshot.get("interaction_mind", {}),
            "critical_logic_points": snapshot.get("critical_points", []),
        }

    def _get_prompt(self) -> str:
        return (
            "You are Zentex. This is a capability enhancement patch for Q7 (门控确认).\n"
            "Analyze the current reasoning flow to output an additive patch for:\n"
            "1) specific high-stakes nodes requiring manual human approval\n"
            "2) uncertainty thresholds for automated execution\n"
            "3) human-in-the-loop recommendation points\n"
            "Return STRICT JSON with keys: patch_summary, patch_updates.\n"
        )


def build_q7_gate_confirmation_patch_plugin(
    *,
    plugin_id: str = "nine-question-q7-gate-confirmation-patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q7GateConfirmationPatchPlugin:
    return Q7GateConfirmationPatchPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code="nine_questions.q7",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        tool_type="nine_question_capability_patch",
        purpose="Additive gate refinement for Q7.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["patch_summary", "patch_updates"]},
        required_context=["context_snapshot", "transcript_store", "model_provider"],
        trigger_conditions=["gate_logic"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=False,
        rollback_conditions=["q7_patch_regression"],
        revocation_reasons=[],
        do_not_use_when=["missing_model_provider"],
    )
