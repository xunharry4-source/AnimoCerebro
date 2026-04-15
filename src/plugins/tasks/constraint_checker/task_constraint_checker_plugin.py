from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.tasks.service import task_plugin_check_constraints


_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class TaskConstraintCheckerPlugin(FunctionalPluginSpec):
    behavior_key: str = "task.constraint_checking"
    display_name: str = "Task Constraint Checker"
    description: str = "Check execution constraints for a task before dispatch."
    capability_tags: List[str] = Field(
        default_factory=lambda: [
            "task.constraint_checking",
            "dispatch.constraint_checking",
            "routing.safety_evidence",
        ]
    )

    @classmethod
    def plugin_kind(cls) -> str:
        return "task_constraint_checker"

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return task_plugin_check_constraints(
            constraints=parameters.get("constraints") or {},
            runtime_context=parameters.get("runtime_context") or {},
        )


def build_task_constraint_checker_plugin(
    *,
    plugin_id: str = "task_constraint_checker",
    version: str = "1.0.0",
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> TaskConstraintCheckerPlugin:
    return TaskConstraintCheckerPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="tasks.dispatch.constraint_checker",
        is_concurrency_safe=True,
        lifecycle_status=lifecycle_status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["constraint_check_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )

TaskConstraintCheckerPlugin.model_rebuild()
