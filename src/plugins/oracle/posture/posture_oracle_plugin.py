from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.models import PluginLifecycleStatus


class BaselinePostureOracle(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "oracle_posture"
    version: str = "1.0.0"
    feature_code: str = "oracle.posture"
    display_name: str = "Posture Oracle"
    description: str = "Return a safe operating posture for the current decision trace."
    behavior_key: str = "oracle_posture"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["posture_regression"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def apply_posture(self, decision_trace: dict[str, Any]) -> dict[str, Any]:
        return {
            "evaluation_style": "evidence_first",
            "risk_tolerance": "low",
            "confirmation_strategy": "confirm_on_write",
            "action_rhythm": "bounded_incremental_steps",
            "decision_trace": decision_trace,
        }


def build_default_posture_oracle() -> BaselinePostureOracle:
    return BaselinePostureOracle()
