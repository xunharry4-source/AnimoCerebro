from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)
from zentex.tasks.service import task_plugin_extract_evidence


class TaskEvidenceExtractorPlugin(FunctionalPluginSpec):
    behavior_key: str = "task.evidence_extraction"
    display_name: str = "Task Evidence Extractor"
    description: str = "Extract structured evidence from raw task execution output."
    capability_tags: List[str] = Field(
        default_factory=lambda: [
            "task.evidence_extraction",
            "verification.evidence_extraction",
            "supervision.signal_extraction",
        ]
    )

    @classmethod
    def plugin_kind(cls) -> str:
        return "task_evidence_extractor"

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        result = parameters.get("result") or {}
        return task_plugin_extract_evidence(
            result,
            source_kind=str(parameters.get("source_kind") or result.get("source_kind") or "generic"),
        )


def build_task_evidence_extractor_plugin(
    *,
    plugin_id: str = "task_evidence_extractor",
    version: str = "1.0.0",
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> TaskEvidenceExtractorPlugin:
    return TaskEvidenceExtractorPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="tasks.verification.evidence_extractor",
        is_concurrency_safe=True,
        lifecycle_status=lifecycle_status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["evidence_extraction_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )

TaskEvidenceExtractorPlugin.model_rebuild()
