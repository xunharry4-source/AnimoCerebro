from __future__ import annotations

from typing import Any

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.plugin_family import ObjectiveSpec


class BaselineObjectiveOracle(ObjectiveSpec):
    plugin_id: str = "baseline_objective_oracle"
    version: str = "1.0.0"
    feature_code: str = "objective.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["objective_queue_regression"]
    revocation_reasons: list[str] = []

    def refine_task_queue(self, task_queue: list[Any], context: dict[str, Any]) -> list[Any]:
        if not isinstance(task_queue, list):
            return []
        return list(task_queue)


def build_default_objective_oracle() -> BaselineObjectiveOracle:
    return BaselineObjectiveOracle()
