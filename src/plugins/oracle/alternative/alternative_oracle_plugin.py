from __future__ import annotations

from typing import Any

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.plugin_family import AlternativeSpec


class BaselineAlternativeOracle(AlternativeSpec):
    plugin_id: str = "baseline_alternative_oracle"
    version: str = "1.0.0"
    feature_code: str = "alternative.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["alternative_strategy_regression"]
    revocation_reasons: list[str] = []

    def get_downgrade_options(self, block_context: dict[str, Any]) -> list[Any]:
        blocked = block_context.get("blocked_reason") or block_context.get("reason") or "primary_path_blocked"
        return [
            {
                "strategy": "read_only_audit_mode",
                "trigger": blocked,
                "cost": "low",
            },
            {
                "strategy": "request_human_confirmation",
                "trigger": "write_or_permission_boundary_detected",
                "cost": "medium",
            },
            {
                "strategy": "collect_more_evidence_then_replan",
                "trigger": "insufficient_confidence",
                "cost": "medium",
            },
        ]


def build_default_alternative_oracle() -> BaselineAlternativeOracle:
    return BaselineAlternativeOracle()
