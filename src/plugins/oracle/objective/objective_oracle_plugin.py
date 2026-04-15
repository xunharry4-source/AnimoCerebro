from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.models import PluginLifecycleStatus


class BaselineObjectiveOracle(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "oracle_objective"
    version: str = "1.0.0"
    feature_code: str = "oracle.objective"
    display_name: str = "Objective Oracle"
    description: str = "Refine objective queues into a stable priority order."
    behavior_key: str = "oracle_objective"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["objective_queue_regression"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def refine_task_queue(self, task_queue: list[Any], context: dict[str, Any]) -> list[Any]:
        if not isinstance(task_queue, list):
            return []
        return sorted(
            list(task_queue),
            key=lambda item: (
                int((item or {}).get("priority", 999)) if isinstance(item, dict) else 999,
                str((item or {}).get("id", "")) if isinstance(item, dict) else "",
            ),
        )


def build_default_objective_oracle() -> BaselineObjectiveOracle:
    return BaselineObjectiveOracle()
