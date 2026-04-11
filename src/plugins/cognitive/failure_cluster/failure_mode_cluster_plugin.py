from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.memory import (
    ConsolidationPluginOutput,
    ForgettableNoiseRule,
    MemoryPromotionCandidate,
    PatternStabilityScore,
)


class FailureModeClusterPlugin(CognitiveToolSpec):
    """Cluster repeated failure reflections into reusable lesson/pattern candidates."""

    def analyze_memory(
        self,
        *,
        context: Dict[str, Any],
        noise_rules: List[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        del noise_rules
        refs = list(context.get("input_memory_refs") or [])
        topic_counter: Counter[str] = Counter()
        candidates: List[MemoryPromotionCandidate] = []
        pattern_scores: List[PatternStabilityScore] = []
        compressed_refs: List[str] = []

        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_id = str(ref.get("ref_id") or "unknown-ref")
            summary = str(ref.get("summary") or ref.get("text") or "")
            topic = str(ref.get("topic") or "general_failure")
            if "failure" not in summary.lower() and "timeout" not in summary.lower():
                continue
            topic_counter[topic] += 1
            compressed_refs.append(ref_id)
            candidates.append(
                MemoryPromotionCandidate(
                    source_ref=ref_id,
                    candidate_type="lesson",
                    stability_score=0.74,
                    reuse_value=0.81,
                    promotion_reason=f"Repeated failure trace suggests a reusable lesson around {topic}.",
                )
            )

        for topic, frequency in topic_counter.items():
            pattern_scores.append(
                PatternStabilityScore(
                    pattern_id=f"pattern:{topic}",
                    frequency=frequency,
                    time_span_seconds=3600,
                    cross_context_reuse=0.7,
                    conflict_count=0,
                    stability_score=min(1.0, 0.45 + 0.1 * frequency),
                )
            )

        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            promotion_candidates=candidates,
            compressed_refs=compressed_refs,
            pattern_scores=pattern_scores,
        )


def build_failure_mode_cluster_plugin(
    *,
    plugin_id: str = "failure-mode-cluster",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> FailureModeClusterPlugin:
    """Build the default failure clustering plugin for offline memory consolidation."""
    return FailureModeClusterPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["consolidation_false_promotion_spike"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="memory_failure_cluster",
        purpose="Cluster repeated failure traces into reusable lessons and stable patterns.",
        input_schema={"type": "object", "required": ["input_memory_refs"]},
        output_schema={"type": "object", "required": ["promotion_candidates", "pattern_scores"]},
        required_context=["input_memory_refs"],
        trigger_conditions=["sleep_phase", "reflection_postprocess", "memory_governance_review"],
        behavior_key="memory_consolidation",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["execution_requested", "unsafe_external_action"],
    )
