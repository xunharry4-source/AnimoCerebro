from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from zentex.common.plugin_ids import COGNITIVE_FAILURE_CLUSTER
from zentex.memory import (
    ConsolidationPluginOutput,
    ForgettableNoiseRule,
    MemoryPromotionCandidate,
    PatternStabilityScore,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


class FailureModeClusterPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = COGNITIVE_FAILURE_CLUSTER
    version: str = "1.0.0"
    feature_code: str = "cognitive.failure_cluster"
    display_name: str = "Failure Mode Cluster"
    description: str = "Cluster repeated failure reflections into reusable patterns."
    behavior_key: str = "memory_consolidation"
    lifecycle_status: str = "active"
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def analyze_memory(
        self,
        *,
        context: dict[str, Any],
        noise_rules: list[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        del noise_rules
        refs = list(context.get("input_memory_refs") or [])
        topic_counter: Counter[str] = Counter()
        candidates: list[MemoryPromotionCandidate] = []
        pattern_scores: list[PatternStabilityScore] = []
        compressed_refs: list[str] = []
        plugin_service = context.get("plugin_service")
        functional_inputs: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_inputs = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=dict(context),
                trace_id=str(context.get("trace_id") or "failure-cluster"),
                originator_id=str(context.get("session_id") or "failure-cluster"),
                caller_plugin_id=self.plugin_id,
            )

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

        for item in functional_inputs:
            if item.get("status") != "done":
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            compressed_refs.extend(str(ref_id) for ref_id in result.get("compressed_refs", []) or [])

        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            promotion_candidates=candidates,
            compressed_refs=sorted(set(compressed_refs)),
            pattern_scores=pattern_scores,
        )


def build_failure_mode_cluster_plugin() -> FailureModeClusterPlugin:
    return FailureModeClusterPlugin()
