from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.tasks import task_plugin_match_capabilities


class TaskCapabilityMatcherPlugin(FunctionalPluginSpec):
    behavior_key: str = "task.capability_matching"
    display_name: str = "Task Capability Matcher"
    description: str = "Compare required task capabilities to candidate capabilities."
    capability_tags: List[str] = Field(
        default_factory=lambda: [
            "task.capability_matching",
            "dispatch.capability_matching",
            "routing.evidence",
        ]
    )

    @classmethod
    def plugin_kind(cls) -> str:
        return "task_capability_matcher"

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return task_plugin_match_capabilities(
            required_capabilities=parameters.get("required_capabilities") or [],
            candidate_capabilities=parameters.get("candidate_capabilities") or [],
            preferred_capabilities=parameters.get("preferred_capabilities") or [],
            forbidden_capabilities=parameters.get("forbidden_capabilities") or [],
            capability_aliases=parameters.get("capability_aliases") or {},
        )


def build_task_capability_matcher_plugin(
    *,
    plugin_id: str = "task_capability_matcher",
    version: str = "1.0.0",
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> TaskCapabilityMatcherPlugin:
    return TaskCapabilityMatcherPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="tasks.dispatch.capability_matcher",
        is_concurrency_safe=True,
        lifecycle_status=lifecycle_status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["capability_match_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )

TaskCapabilityMatcherPlugin.model_rebuild()
