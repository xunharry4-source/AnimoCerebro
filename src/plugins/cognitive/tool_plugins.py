from __future__ import annotations

from typing import Any, Dict, List

from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult


class TaskDecomposerPlugin(CognitiveToolSpec):
    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        task_description = str(
            context.get("task_description")
            or context.get("goal_description")
            or "Unnamed multi-stage task"
        )
        goal_stages = context.get("goal_stages")
        if isinstance(goal_stages, list) and goal_stages:
            stages = [str(stage).strip() for stage in goal_stages if str(stage).strip()]
        else:
            stages = [
                part.strip()
                for part in task_description.replace("->", " then ").split(" then ")
                if part.strip()
            ]
        subtasks = [
            {"step": index + 1, "title": stage}
            for index, stage in enumerate(stages)
        ]
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Task decomposed into sub-steps",
            proposals=[
                {
                    "kind": "subtask_plan",
                    "subtasks": subtasks,
                }
            ],
            context_updates={
                "subtasks": subtasks,
                "decomposition_summary": f"{len(subtasks)} staged steps identified",
            },
            confidence=0.82,
        )


class RiskComparatorPlugin(CognitiveToolSpec):
    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        candidate_paths = context.get("candidate_paths", [])
        ranked_options: List[Dict[str, Any]] = []
        risks: List[Dict[str, Any]] = []
        for path in candidate_paths:
            if not isinstance(path, dict):
                continue
            option_id = str(path.get("option_id") or path.get("title") or "option")
            risk_score = int(path.get("risk_score", 50))
            ranked_options.append(
                {
                    "option_id": option_id,
                    "risk_score": risk_score,
                    "recommended": False,
                }
            )
            risks.append(
                {
                    "option_id": option_id,
                    "risk_level": "high" if risk_score >= 70 else "moderate",
                    "reason": str(path.get("risk_reason") or "comparative assessment"),
                }
            )
        ranked_options.sort(key=lambda item: item["risk_score"])
        if ranked_options:
            ranked_options[0]["recommended"] = True
        conservative_option = ranked_options[0]["option_id"] if ranked_options else None
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Risk trade-offs compared across candidate paths",
            ranked_options=ranked_options,
            risks=risks,
            proposals=[
                {
                    "kind": "conservative_alternative",
                    "option_id": conservative_option,
                }
            ],
            context_updates={
                "risk_ranking": ranked_options,
                "conservative_alternative": conservative_option,
            },
            confidence=0.78,
        )


def build_task_decomposer_plugin(
    *,
    plugin_id: str = "task-decomposer",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> TaskDecomposerPlugin:
    return TaskDecomposerPlugin(
        plugin_id=plugin_id,
        version=version,
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["decomposition_regression_detected"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="task_decomposer",
        purpose="Break multi-stage goals into auditable subtasks.",
        input_schema={"type": "object", "required": ["task_description"]},
        output_schema={"type": "object", "required": ["subtasks"]},
        required_context=["task_description"],
        trigger_conditions=["multi_stage_goal"],
        behavior_key="task_decomposition",
        supports_multi_active=False,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["execution_requested", "unsafe_external_action"],
    )


def build_risk_comparator_plugin(
    *,
    plugin_id: str = "risk-comparator",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> RiskComparatorPlugin:
    return RiskComparatorPlugin(
        plugin_id=plugin_id,
        version=version,
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["ranking_regression_detected"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="risk_comparator",
        purpose="Compare candidate reasoning paths and propose a conservative alternative.",
        input_schema={"type": "object", "required": ["candidate_paths"]},
        output_schema={"type": "object", "required": ["risk_ranking"]},
        required_context=["candidate_paths"],
        trigger_conditions=["multiple_candidate_paths"],
        behavior_key="risk_assessment",
        supports_multi_active=False,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["execution_requested", "unsafe_external_action"],
    )
