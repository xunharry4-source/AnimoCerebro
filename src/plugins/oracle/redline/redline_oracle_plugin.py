from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.models import PluginLifecycleStatus


class BaselineRedlineOracle(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "oracle_redline"
    version: str = "1.0.0"
    feature_code: str = "oracle.redline"
    display_name: str = "Redline Oracle"
    description: str = "Return forbidden zones and critical redlines."
    behavior_key: str = "oracle_redline"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["redline_regression"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def get_forbidden_zones(self) -> list[dict[str, Any]]:
        return [
            {
                "zone": "state_fabrication",
                "severity": "critical",
                "forbidden_actions": [
                    "fake_runtime_state",
                    "hide_plugin_failure",
                    "skip_audit_logging",
                ],
            },
            {
                "zone": "unsafe_execution",
                "severity": "high",
                "forbidden_actions": [
                    "unconfirmed_destructive_write",
                    "silent_external_side_effect",
                ],
            },
        ]


def build_default_redline_oracle() -> BaselineRedlineOracle:
    return BaselineRedlineOracle()
