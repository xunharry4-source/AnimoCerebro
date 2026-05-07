from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q9_how_should_i_act.external.service import (
    run_q9_external_llm_and_save,
)
from plugins.nine_questions.q9_how_should_i_act.internal.service import (
    run_q9_internal_llm_and_save,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q9
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class Q9HowShouldIActPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q9
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q9"
    display_name: str = "Q9: 我应该如何行动"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_internal_action_design(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q9")
        internal_run = start_module_run(
            module_runs,
            "q9_internal_action_llm",
            source="plugins.nine_questions.q9.internal",
        )
        try:
            internal = run_q9_internal_llm_and_save(context)
            finish_module_run(internal_run)
        except Exception as exc:
            fail_module_run(internal_run, error_code="q9_internal_action_failed", error_message=str(exc))
            raise

        return CognitiveToolResult(
            tool_id=f"{self.plugin_id}:internal",
            summary="Q9 internal action design saved as a validated internal lane result.",
            llm_output={
                "q9_internal_llm_input": internal["llm_input"],
                "q9_internal_llm_output": internal["llm_output"],
            },
            context_updates={
                "q9_internal_action_design": internal["result"],
                "q9_internal_execution_diagnosis": {
                    "authenticity_status": "completed",
                    "diagnosis_code": "internal_action_design_validated",
                    "lane": "internal",
                    "module_runs": list(module_runs),
                    "elapsed_ms": int((perf_counter() - started) * 1000),
                },
            },
            proposals=[
                {"kind": "q9_internal_action_design", **internal["result"]},
            ],
            confidence=0.75,
        )

    def run_external_action_design(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q9")
        external_run = start_module_run(
            module_runs,
            "q9_external_action_llm",
            source="plugins.nine_questions.q9.external",
        )
        try:
            external = run_q9_external_llm_and_save(context)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q9_external_action_failed", error_message=str(exc))
            raise

        return CognitiveToolResult(
            tool_id=f"{self.plugin_id}:external",
            summary="Q9 external action design saved as a validated external lane result.",
            llm_output={
                "q9_external_llm_input": external["llm_input"],
                "q9_external_llm_output": external["llm_output"],
            },
            context_updates={
                "q9_external_action_design": external["result"],
                "q9_external_execution_diagnosis": {
                    "authenticity_status": "completed",
                    "diagnosis_code": "external_action_design_validated",
                    "lane": "external",
                    "module_runs": list(module_runs),
                    "elapsed_ms": int((perf_counter() - started) * 1000),
                },
            },
            proposals=[
                {"kind": "q9_external_action_design", **external["result"]},
            ],
            confidence=0.75,
        )

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        internal_result = self.run_internal_action_design(context)
        external_result = self.run_external_action_design(context)
        internal_runs = (
            internal_result.context_updates.get("q9_internal_execution_diagnosis", {}).get("module_runs", [])
            if isinstance(internal_result.context_updates, dict)
            else []
        )
        external_runs = (
            external_result.context_updates.get("q9_external_execution_diagnosis", {}).get("module_runs", [])
            if isinstance(external_result.context_updates, dict)
            else []
        )
        llm_output = {
            **internal_result.llm_output,
            **external_result.llm_output,
        }
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q9 internal/external action designs are validated and exposed separately.",
            llm_output=llm_output,
            context_updates={
                **llm_output,
                **internal_result.context_updates,
                **external_result.context_updates,
                "q9_execution_diagnosis": {
                    "authenticity_status": "completed",
                    "diagnosis_code": "separate_internal_external_action_designs_validated",
                    "module_runs": list(internal_runs) + list(external_runs),
                    "elapsed_ms": int((perf_counter() - started) * 1000),
                },
            },
            proposals=list(internal_result.proposals) + list(external_result.proposals),
            confidence=0.75,
        )


def build_q9_how_should_i_act_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q9,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q9HowShouldIActPlugin:
    return Q9HowShouldIActPlugin(
        plugin_id=plugin_id,
        version=version,
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )
