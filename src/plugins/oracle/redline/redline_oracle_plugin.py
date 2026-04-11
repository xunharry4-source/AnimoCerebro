from __future__ import annotations

from typing import Any

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.plugin_family import RedlinePluginSpec


class BaselineRedlineOracle(RedlinePluginSpec):
    plugin_id: str = "baseline_redline_oracle"
    version: str = "1.0.0"
    feature_code: str = "redline.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["redline_regression"]
    revocation_reasons: list[str] = []

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
