from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.memory import (
    ConsolidationPluginOutput,
    ForgettableNoiseRule,
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
                # 为什么这里按规则显式命中：清理噪音必须可审计，不能靠隐式"感觉像垃圾"。
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
