from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q6_what_should_i_not_do.external.service import (
    run_q6_external_llm_and_save,
)
from plugins.nine_questions.q6_what_should_i_not_do.internal.service import (
    run_q6_internal_llm_and_save,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q6
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class Q6WhatShouldINotDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q6
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q6"
    display_name: str = "Q6: 我不应该做什么"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_internal_consequence_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        return run_q6_internal_llm_and_save(context)["result"]

    def run_external_consequence_profile(self, context: dict[str, Any]) -> dict[str, Any]:
        return run_q6_external_llm_and_save(context)["result"]

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q6")

        internal_run = start_module_run(
            module_runs,
            "q6_internal_consequence_llm",
            source="plugins.nine_questions.q6.internal",
        )
        try:
            internal_profile = self.run_internal_consequence_profile(context)
            finish_module_run(internal_run)
        except Exception as exc:
            fail_module_run(internal_run, error_code="q6_internal_consequence_failed", error_message=str(exc))
            raise

        external_run = start_module_run(
            module_runs,
            "q6_external_consequence_llm",
            source="plugins.nine_questions.q6.external",
        )
        try:
            external_profile = self.run_external_consequence_profile(context)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q6_external_consequence_failed", error_message=str(exc))
            raise

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q6 internal/external consequence LLM inputs and outputs saved separately.",
            context_updates={
                "q6_internal_consequence_profile": internal_profile,
                "q6_external_consequence_profile": external_profile,
                "q6_llm_module_outputs": {
                    "internal_input_module_id": "q6_internal_llm_request",
                    "internal_output_module_id": "q6_internal_consequence_llm",
                    "external_input_module_id": "q6_external_llm_request",
                    "external_output_module_id": "q6_external_consequence_llm",
                },
                "q6_execution_diagnosis": {
                    "authenticity_status": "completed",
                    "diagnosis_code": "internal_external_llm_saved",
                    "module_runs": list(module_runs),
                    "elapsed_ms": int((perf_counter() - started) * 1000),
                },
            },
            confidence=0.75,
        )


def build_q6_what_should_i_not_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q6,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q6WhatShouldINotDoPlugin:
    return Q6WhatShouldINotDoPlugin(
        plugin_id=plugin_id,
        version=version,
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )
