from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.models import PluginLifecycleStatus


class BaselineAlternativeOracle(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "oracle_alternative"
    version: str = "1.0.0"
    feature_code: str = "oracle.alternative"
    display_name: str = "Alternative Oracle"
    description: str = "Return downgrade and fallback strategies when a primary path is blocked."
    behavior_key: str = "oracle_alternative"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["alternative_strategy_regression"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def get_downgrade_options(self, block_context: dict[str, Any]) -> list[dict[str, Any]]:
        blocked = block_context.get("blocked_reason") or block_context.get("reason") or "primary_path_blocked"
        return [
            {"strategy": "read_only_audit_mode", "trigger": blocked, "cost": "low"},
            {"strategy": "request_human_confirmation", "trigger": "write_or_permission_boundary_detected", "cost": "medium"},
            {"strategy": "collect_more_evidence_then_replan", "trigger": "insufficient_confidence", "cost": "medium"},
        ]


def build_default_alternative_oracle() -> BaselineAlternativeOracle:
    return BaselineAlternativeOracle()
