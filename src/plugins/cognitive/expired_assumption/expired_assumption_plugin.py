from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from zentex.common.plugin_ids import COGNITIVE_EXPIRED_ASSUMPTION
from zentex.memory import ConsolidationPluginOutput, ForgettableNoiseRule
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


class ExpiredAssumptionCleanerPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = COGNITIVE_EXPIRED_ASSUMPTION
    version: str = "1.0.0"
    feature_code: str = "cognitive.expired_assumption"
    display_name: str = "Expired Assumption Cleaner"
    description: str = "Mark stale assumptions and duplicate low-value memory as forgettable."
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
        refs = list(context.get("input_memory_refs") or [])
        now = datetime.now(timezone.utc)
        pruned_refs: list[str] = []
        plugin_service = context.get("plugin_service")
        functional_inputs: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_inputs = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=dict(context),
                trace_id=str(context.get("trace_id") or "expired-assumption"),
                originator_id=str(context.get("session_id") or "expired-assumption"),
                caller_plugin_id=self.plugin_id,
            )

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

        for item in functional_inputs:
            if item.get("status") != "done":
                continue
            result = item.get("result")
            if isinstance(result, dict):
                pruned_refs.extend(str(ref_id) for ref_id in result.get("pruned_refs", []) or [])
            elif isinstance(result, list):
                pruned_refs.extend(str(ref_id) for ref_id in result)

        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            pruned_refs=sorted(set(pruned_refs)),
        )


def build_expired_assumption_cleaner_plugin() -> ExpiredAssumptionCleanerPlugin:
    return ExpiredAssumptionCleanerPlugin()
