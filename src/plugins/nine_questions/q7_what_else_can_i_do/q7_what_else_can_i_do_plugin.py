from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q7_what_else_can_i_do.external.service import (
    run_q7_external_llm_and_save,
)
from plugins.nine_questions.q7_what_else_can_i_do.assessment_contract import (
    build_q7_external_context_updates,
    build_q7_internal_context_updates,
)
from plugins.nine_questions.q7_what_else_can_i_do.internal.service import (
    run_q7_internal_llm_and_save,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q7
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class Q7WhatElseCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q7
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q7"
    display_name: str = "Q7: 我还能做什么"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q7")

        internal_run = start_module_run(
            module_runs,
            "q7_internal_creativity_llm",
            source="plugins.nine_questions.q7.internal",
        )
        try:
            internal = run_q7_internal_llm_and_save(context)
            finish_module_run(internal_run)
        except Exception as exc:
            fail_module_run(internal_run, error_code="q7_internal_creativity_failed", error_message=str(exc))
            raise

        external_run = start_module_run(
            module_runs,
            "q7_external_creativity_llm",
            source="plugins.nine_questions.q7.external",
        )
        try:
            external = run_q7_external_llm_and_save(context)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q7_external_creativity_failed", error_message=str(exc))
            raise
        internal_context_updates = build_q7_internal_context_updates(internal["result"])
        external_context_updates = build_q7_external_context_updates(external["result"])

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q7 internal and external creative possibilities normalized and saved in separate module rows.",
            context_updates={
                **internal_context_updates,
                **external_context_updates,
                "q7_execution_diagnosis": {
                    "authenticity_status": "completed",
                    "diagnosis_code": "internal_external_llm_saved",
                    "module_runs": list(module_runs),
                    "elapsed_ms": int((perf_counter() - started) * 1000),
                },
            },
            confidence=0.75,
        )


def build_q7_what_else_can_i_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q7,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q7WhatElseCanIDoPlugin:
    return Q7WhatElseCanIDoPlugin(
        plugin_id=plugin_id,
        version=version,
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )
