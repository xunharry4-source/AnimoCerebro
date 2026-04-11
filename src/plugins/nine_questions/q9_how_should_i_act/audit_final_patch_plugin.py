from __future__ import annotations

from typing import Any, Dict

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.capability_patch_base import BaseCapabilityPatchPlugin


class Q9AuditFinalPatchPlugin(BaseCapabilityPatchPlugin):
    """
    Capability enhancement for Q9 (我是否需要重新确认).
    Focuses on the final audit of the entire nine-question reasoning chain for consistency.
    """
    question_ref: str = "我是否需要重新确认-终审补丁"
    source_module: str = "q9_audit_final_patch"
    invocation_phase: str = "nine_question_q9_patch"

    def _get_local_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = context.get("context_snapshot", {})
        return {
            "nine_question_state": snapshot.get("nine_question_state", {}),
            "decision_summary": snapshot.get("decision_summary", {}),
        }

    def _get_prompt(self) -> str:
        return (
            "You are Zentex. This is a capability enhancement patch for Q9 (终审重校验).\n"
            "Analyze the complete nine-question reasoning chain and output an additive patch for:\n"
            "1) global consistency conflicts (e.g. Q1 vs Q3 vs Decision)\n"
            "2) residue risks not addressed by current plan\n"
            "3) fallback safety actions if the decision fails\n"
            "Return STRICT JSON with keys: patch_summary, patch_updates.\n"
        )


def build_q9_audit_final_patch_plugin(
    *,
    plugin_id: str = "nine-question-q9-audit-final-patch",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q9AuditFinalPatchPlugin:
    return Q9AuditFinalPatchPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        feature_code="nine_questions.q9",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        tool_type="nine_question_capability_patch",
        purpose="Additive final audit refinement for Q9.",
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["patch_summary", "patch_updates"]},
        required_context=["context_snapshot", "transcript_store", "model_provider"],
        trigger_conditions=["re-confirming"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=False,
        rollback_conditions=["q9_patch_regression"],
        revocation_reasons=[],
        do_not_use_when=["missing_model_provider"],
    )
