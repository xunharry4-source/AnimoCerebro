from __future__ import annotations

from typing import Any, Dict, Optional

from zentex.core.model_provider_spec import (
    ModelProviderAuthError,
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderSpec,
    ModelProviderTimeoutError,
)
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.safety.conflict_engine import CognitiveConflictReport


class SemanticConflictPlugin(CognitiveToolSpec):
    def detect_conflict(
        self,
        *,
        context: Dict[str, Any],
        model_provider: ModelProviderSpec,
    ) -> Optional[CognitiveConflictReport]:
        caller_context = ModelProviderCallerContext(
            source_module="CognitiveConflictEngine",
            invocation_phase="semantic_conflict_detection",
            question_driver_refs=["我是谁", "我现在应该做什么", "我受到哪些约束"],
            decision_id=context.get("decision_id"),
        )
        try:
            payload = model_provider.generate_json(
                prompt=(
                    "Assess whether the proposed goal conflicts with identity constraints. "
                    "Return JSON with keys has_conflict, severity, suggested_resolution, rationale."
                ),
                context=context,
                caller_context=caller_context,
            )
        except (
            ModelProviderConfigError,
            ModelProviderAuthError,
            ModelProviderTimeoutError,
            ModelProviderRateLimitError,
            ModelProviderRemoteError,
            ModelProviderError,
        ):
            raise

        if not payload.get("has_conflict"):
            return None
        return CognitiveConflictReport(
            conflict_type="semantic_identity_conflict",
            severity=str(payload.get("severity") or "high"),
            suggested_resolution=str(
                payload.get("suggested_resolution") or "pause_and_review_identity_alignment"
            ),
            source_plugin_id=self.plugin_id,
            details={
                "rationale": payload.get("rationale"),
                "goal": context.get("goal"),
                "identity_constraints": context.get("identity_constraints"),
            },
        )


def build_semantic_conflict_plugin(
    *,
    plugin_id: str = "semantic-conflict",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> SemanticConflictPlugin:
    return SemanticConflictPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["semantic_conflict_false_positive_spike"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="semantic_conflict_detector",
        purpose="Detect conflicts between active goals and identity constraints with live model inference.",
        input_schema={"type": "object", "required": ["goal", "identity_constraints"]},
        output_schema={"type": "object", "required": ["has_conflict"]},
        required_context=["goal", "identity_constraints"],
        trigger_conditions=["always"],
        behavior_key="cognitive_conflict_detection",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["missing_model_provider", "execution_requested"],
    )
