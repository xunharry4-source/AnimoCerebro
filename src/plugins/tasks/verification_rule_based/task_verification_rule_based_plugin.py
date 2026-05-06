from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.tasks import task_plugin_rule_based_verification


class TaskRuleBasedVerificationPlugin(FunctionalPluginSpec):
    behavior_key: str = "task.verification"
    display_name: str = "Task Rule-Based Verification"
    description: str = "Validate task results against deterministic verification rules."
    capability_tags: List[str] = Field(
        default_factory=lambda: [
            "task.verification",
            "verification.rule_based",
            "result.validation",
        ]
    )

    @classmethod
    def plugin_kind(cls) -> str:
        return "task_verifier"

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return task_plugin_rule_based_verification(
            parameters.get("result") or {},
            rules=parameters.get("rules") or [],
        )


def build_task_rule_based_verification_plugin(
    *,
    plugin_id: str = "task_verification_rule_based",
    version: str = "1.0.0",
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> TaskRuleBasedVerificationPlugin:
    return TaskRuleBasedVerificationPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="tasks.verification.rule_based",
        is_concurrency_safe=True,
        lifecycle_status=lifecycle_status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["task_verification_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )

TaskRuleBasedVerificationPlugin.model_rebuild()
