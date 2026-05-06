from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from pydantic import Field

from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.tasks import task_plugin_plan_compensation


class TaskCompensationWorkspaceCleanupPlugin(FunctionalPluginSpec):
    behavior_key: str = "task.compensation"
    display_name: str = "Task Compensation Workspace Cleanup"
    description: str = "Create a safe compensation cleanup plan for temporary task artifacts."
    capability_tags: List[str] = Field(
        default_factory=lambda: [
            "task.compensation",
            "compensation.workspace_cleanup",
            "supervision.cleanup_planning",
        ]
    )

    @classmethod
    def plugin_kind(cls) -> str:
        return "task_compensation"

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return task_plugin_plan_compensation(
            workspace=str(parameters.get("workspace") or "."),
            artifacts=parameters.get("artifacts") or [],
            failure_type=str(parameters.get("failure_type") or "execution_error"),
        )


def build_task_compensation_workspace_cleanup_plugin(
    *,
    plugin_id: str = "task_compensation_workspace_cleanup",
    version: str = "1.0.0",
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> TaskCompensationWorkspaceCleanupPlugin:
    return TaskCompensationWorkspaceCleanupPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="tasks.compensation.workspace_cleanup",
        is_concurrency_safe=True,
        lifecycle_status=lifecycle_status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["compensation_plan_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )

TaskCompensationWorkspaceCleanupPlugin.model_rebuild()
