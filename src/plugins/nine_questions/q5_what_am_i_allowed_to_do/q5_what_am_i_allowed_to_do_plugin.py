from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q5_what_am_i_allowed_to_do.external.service import (
    run_q5_external_llm_and_save,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.internal.service import (
    run_q5_internal_llm_and_save,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q5
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class Q5WhatAmIAllowedToDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q5
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q5"
    display_name: str = "Q5: 我被允许做什么"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_internal_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q5")
        internal_run = start_module_run(
            module_runs,
            "q5_internal_authorization_llm",
            source="plugins.nine_questions.q5.internal",
        )
        try:
            internal = run_q5_internal_llm_and_save(context)
            finish_module_run(internal_run)
        except Exception as exc:
            fail_module_run(internal_run, error_code="q5_internal_authorization_failed", error_message=str(exc))
            raise

        llm_output = {
            "q5_internal_llm_input": internal["llm_input"],
            "q5_internal_llm_output": internal["llm_output"],
        }
        context_updates = {
            "q5_internal_cannot_do_boundary": internal["result"],
            "q5_internal_authorization_boundary": internal["result"],
            "q5_internal_execution_diagnosis": {
                "authenticity_status": "completed",
                "diagnosis_code": "internal_llm_saved",
                "lane": "internal",
                "module_runs": list(module_runs),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        }
        return CognitiveToolResult(
            tool_id=f"{self.plugin_id}:internal",
            summary="Q5 internal cannot-do boundary saved as a normalized internal lane result.",
            llm_output=llm_output,
            context_updates=context_updates,
            proposals=[
                {"kind": "q5_internal_cannot_do_boundary", **internal["result"]},
            ],
            confidence=0.75,
        )

    def run_external_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q5")
        external_run = start_module_run(
            module_runs,
            "q5_external_authorization_llm",
            source="plugins.nine_questions.q5.external",
        )
        try:
            external = run_q5_external_llm_and_save(context)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q5_external_authorization_failed", error_message=str(exc))
            raise

        llm_output = {
            "q5_external_llm_input": external["llm_input"],
            "q5_external_llm_output": external["llm_output"],
        }
        context_updates = {
            "q5_external_cannot_do_boundary": external["result"],
            "q5_external_authorization_boundary": external["result"],
            "q5_external_execution_diagnosis": {
                "authenticity_status": "completed",
                "diagnosis_code": "external_llm_saved",
                "lane": "external",
                "module_runs": list(module_runs),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        }
        return CognitiveToolResult(
            tool_id=f"{self.plugin_id}:external",
            summary="Q5 external cannot-do boundary saved as a normalized external lane result.",
            llm_output=llm_output,
            context_updates=context_updates,
            proposals=[
                {"kind": "q5_external_cannot_do_boundary", **external["result"]},
            ],
            confidence=0.75,
        )

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        internal_result = self.run_internal_tool(context)
        external_result = self.run_external_tool(context)
        internal_runs = (
            internal_result.context_updates.get("q5_internal_execution_diagnosis", {}).get("module_runs", [])
            if isinstance(internal_result.context_updates, dict)
            else []
        )
        external_runs = (
            external_result.context_updates.get("q5_external_execution_diagnosis", {}).get("module_runs", [])
            if isinstance(external_result.context_updates, dict)
            else []
        )
        llm_output = {
            **internal_result.llm_output,
            **external_result.llm_output,
        }
        context_updates = {
            **internal_result.context_updates,
            **external_result.context_updates,
            "q5_execution_diagnosis": {
                "authenticity_status": "completed",
                "diagnosis_code": "separate_internal_external_lanes_saved",
                "module_runs": list(internal_runs) + list(external_runs),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        }
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q5 internal/external authorization LLM inputs and outputs saved separately.",
            llm_output=llm_output,
            context_updates=context_updates,
            proposals=list(internal_result.proposals) + list(external_result.proposals),
            confidence=0.75,
        )


def build_q5_what_am_i_allowed_to_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q5,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q5WhatAmIAllowedToDoPlugin:
    return Q5WhatAmIAllowedToDoPlugin(
        plugin_id=plugin_id,
        version=version,
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )
