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
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["redline_regression"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def get_forbidden_zones(self) -> dict[str, Any]:
        """Return structured non-bypassable constraints for the cognitive kernel."""
        return {
            "pack_type": "redline_pack",
            "provenance": f"{self.plugin_id} v{self.version}",
            "non_bypassable_constraints": [
                {
                    "zone": "state_fabrication",
                    "severity": "critical",
                    "reason": "Maintaining source of truth integrity is an absolute identity constraint.",
                    "forbidden_actions": [
                        "fake_runtime_state",
                        "hide_plugin_failure",
                        "skip_audit_logging",
                    ],
                },
                {
                    "zone": "unsafe_execution",
                    "severity": "high",
                    "reason": "Unconfirmed destructive operations violate the safe-by-default posture.",
                    "forbidden_actions": [
                        "unconfirmed_destructive_write",
                        "silent_external_side_effect",
                    ],
                },
            ],
            "global_audit_rules": [
                "all_state_mutations_must_be_logged",
                "identity_override_requires_mfa"
            ]
        }


def build_default_redline_oracle() -> BaselineRedlineOracle:
    return BaselineRedlineOracle()
