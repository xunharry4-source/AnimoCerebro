from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q4_what_can_i_do.external.service import (
    run_q4_external_llm_and_save,
)
from plugins.nine_questions.q4_what_can_i_do.internal.service import (
    run_q4_internal_llm_and_save,
)
from plugins.nine_questions.q4_what_can_i_do.manual_goals import (
    empty_manual_task_goal_lane_analysis,
    resolve_workspace_task_goals,
    run_q4_manual_task_goal_lane_analysis_and_save,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q4
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class Q4WhatCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q4
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q4"
    display_name: str = "Q4: 我能做什么"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q4")
        manual_task_goals = resolve_workspace_task_goals(context)
        manual_goal_analysis = {
            "manual_task_goals": [],
            "result": empty_manual_task_goal_lane_analysis(),
        }
        if manual_task_goals:
            manual_goal_run = start_module_run(
                module_runs,
                "q4_manual_task_goal_lane_analysis_llm",
                source="plugins.nine_questions.q4.manual_task_goals",
            )
            try:
                manual_goal_analysis = run_q4_manual_task_goal_lane_analysis_and_save(context)
                finish_module_run(manual_goal_run)
            except Exception as exc:
                fail_module_run(
                    manual_goal_run,
                    error_code="q4_manual_task_goal_lane_analysis_failed",
                    error_message=str(exc),
                )
                raise

        q4_llm_context = {
            **context,
            "UserManualTaskGoalLaneAnalysis": manual_goal_analysis["result"],
        }

        internal_run = start_module_run(
            module_runs,
            "q4_internal_objective_candidate_llm",
            source="plugins.nine_questions.q4.internal",
        )
        try:
            internal = run_q4_internal_llm_and_save(q4_llm_context)
            finish_module_run(internal_run)
        except Exception as exc:
            fail_module_run(internal_run, error_code="q4_internal_objective_candidate_failed", error_message=str(exc))
            raise

        external_run = start_module_run(
            module_runs,
            "q4_external_objective_candidate_llm",
            source="plugins.nine_questions.q4.external",
        )
        try:
            external = run_q4_external_llm_and_save(q4_llm_context)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q4_external_objective_candidate_failed", error_message=str(exc))
            raise

        llm_output = {}
        if manual_goal_analysis.get("llm_input"):
            llm_output["q4_manual_task_goal_analysis_llm_input"] = manual_goal_analysis["llm_input"]
        if manual_goal_analysis.get("llm_output"):
            llm_output["q4_manual_task_goal_analysis_llm_output"] = manual_goal_analysis["llm_output"]
        llm_output.update({
            "q4_internal_llm_input": internal["llm_input"],
            "q4_internal_llm_output": internal["llm_output"],
            "q4_external_llm_input": external["llm_input"],
            "q4_external_llm_output": external["llm_output"],
        })
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q4 internal/external objective-candidate LLM inputs and outputs saved separately.",
            llm_output=llm_output,
            context_updates={
                "q4_user_manual_task_goals": manual_goal_analysis.get("manual_task_goals", []),
                "q4_user_manual_task_goal_lane_analysis": manual_goal_analysis["result"],
                "q4_internal_objective_candidates": internal["result"],
                "q4_internal_objective_semantic_guard": internal.get("semantic_guard", {}),
                "q4_external_objective_candidates": external["result"],
                "q4_external_objective_semantic_guard": external.get("semantic_guard", {}),
                "q4_objective_candidate_set": {
                    "internal": internal["result"],
                    "external": external["result"],
                    "user_manual_task_goal_lane_analysis": manual_goal_analysis["result"],
                },
                "q4_execution_diagnosis": {
                    "authenticity_status": "completed",
                    "diagnosis_code": "internal_external_objective_llm_saved",
                    "module_runs": list(module_runs),
                    "elapsed_ms": int((perf_counter() - started) * 1000),
                },
            },
            confidence=0.75,
        )


def build_q4_what_can_i_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q4,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q4WhatCanIDoPlugin:
    return Q4WhatCanIDoPlugin(
        plugin_id=plugin_id,
        version=version,
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )
