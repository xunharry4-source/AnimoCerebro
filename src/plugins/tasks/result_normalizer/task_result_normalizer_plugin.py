from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List

from pydantic import Field

from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.tasks.service import task_plugin_normalize_result


class TaskResultNormalizerPlugin(FunctionalPluginSpec):
    behavior_key: str = "task.result_normalization"
    display_name: str = "Task Result Normalizer"
    description: str = "Normalize task outputs into a stable envelope."
    capability_tags: List[str] = Field(
        default_factory=lambda: [
            "task.result_normalization",
            "result.normalization",
            "evidence.extraction",
        ]
    )

    @classmethod
    def plugin_kind(cls) -> str:
        return "task_result_normalizer"

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return task_plugin_normalize_result(
            parameters.get("result"),
            source_kind=str(parameters.get("source_kind") or "generic"),
            metadata=parameters.get("metadata") or {},
        )


def build_task_result_normalizer_plugin(
    *,
    plugin_id: str = "task_result_normalizer",
    version: str = "1.0.0",
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> TaskResultNormalizerPlugin:
    return TaskResultNormalizerPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="tasks.result.normalizer",
        is_concurrency_safe=True,
        lifecycle_status=lifecycle_status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["result_normalization_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )

TaskResultNormalizerPlugin.model_rebuild()
