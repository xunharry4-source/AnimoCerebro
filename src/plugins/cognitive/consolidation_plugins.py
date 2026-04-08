from __future__ import annotations

"""
Consolidation analysis plugins / 记忆巩固分析插件。

这些插件只负责为 B8 提供只读分析结果，绝对不允许直接删除、执行或外发。
真正的状态提交由 ConsolidationEngine 在乐观锁校验通过后统一完成。
"""

from collections import Counter
from datetime import datetime, timezone
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


class ExpiredAssumptionCleanerPlugin(CognitiveToolSpec):
    """Find stale assumptions and low-value duplicate references that may be forgotten."""

    def analyze_memory(
        self,
        *,
        context: Dict[str, Any],
        noise_rules: List[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        refs = list(context.get("input_memory_refs") or [])
        now = datetime.now(timezone.utc)
        pruned_refs: List[str] = []

        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_id = str(ref.get("ref_id") or "unknown-ref")
            created_at_raw = ref.get("created_at")
            created_at = created_at_raw if isinstance(created_at_raw, datetime) else now
            age_seconds = int((now - created_at).total_seconds())
            reuse_value = float(ref.get("reuse_value") or 0.0)
            confidence = float(ref.get("confidence") or 0.0)
            noise_kind = str(ref.get("noise_kind") or "")
            is_duplicate = bool(ref.get("is_duplicate", False))

            for rule in noise_rules:
                # 为什么这里按规则显式命中：清理噪音必须可审计，不能靠隐式“感觉像垃圾”。
                if noise_kind != rule.noise_kind and not (
                    rule.noise_kind == "duplicate_case" and is_duplicate
                ):
                    continue
                if age_seconds < rule.age_threshold_seconds:
                    continue
                if reuse_value > rule.reuse_threshold:
                    continue
                if confidence > rule.confidence_threshold:
                    continue
                pruned_refs.append(ref_id)
                break

        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            pruned_refs=pruned_refs,
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


def build_expired_assumption_cleaner_plugin(
    *,
    plugin_id: str = "expired-assumption-cleaner",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> ExpiredAssumptionCleanerPlugin:
    """Build the default assumption-cleaning plugin for offline memory consolidation."""
    return ExpiredAssumptionCleanerPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["forgetting_regression_detected"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="memory_noise_cleaner",
        purpose="Mark stale assumptions and duplicate low-value memory as safely forgettable.",
        input_schema={"type": "object", "required": ["input_memory_refs", "noise_rules"]},
        output_schema={"type": "object", "required": ["pruned_refs"]},
        required_context=["input_memory_refs", "noise_rules"],
        trigger_conditions=["sleep_phase", "agenda_cleanup", "memory_governance_review"],
        behavior_key="memory_consolidation",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["execution_requested", "unsafe_external_action"],
    )
