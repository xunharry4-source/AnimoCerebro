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
from plugins.nine_questions.q6_what_should_i_not_do.llm_output_table import (
    load_external_llm_output_from_table as load_q6_external_llm_output_from_table,
    load_internal_llm_output_from_table as load_q6_internal_llm_output_from_table,
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

    def run_internal_creative_profile(self, context: dict[str, Any], q6_result: dict[str, Any]) -> dict[str, Any]:
        q7_res = run_q7_internal_llm_and_save(context)["result"]
        q6_items = q6_result.get("constraints_by_objective", [])
        if not isinstance(q6_items, list):
            return q7_res

        q6_map = {item.get("objective_number"): item for item in q6_items if item.get("objective_number")}
        q7_possibilities = q7_res.get("creative_possibilities", [])
        if not isinstance(q7_possibilities, list):
            return q7_res

        merged = []
        for q7_item in q7_possibilities:
            num = q7_item.get("objective_number")
            if num and num in q6_map:
                merged.append({**q6_map[num], **q7_item})
            else:
                merged.append(q7_item)
        return {**q7_res, "creative_possibilities": merged}

    def run_external_creative_profile(self, context: dict[str, Any], q6_result: dict[str, Any]) -> dict[str, Any]:
        q7_res = run_q7_external_llm_and_save(context)["result"]
        q6_items = q6_result.get("objective_constraints", [])
        if not isinstance(q6_items, list):
            return q7_res

        q6_map = {item.get("objective_number"): item for item in q6_items if item.get("objective_number")}
        q7_possibilities = q7_res.get("creative_possibilities", [])
        if not isinstance(q7_possibilities, list):
            return q7_res

        merged = []
        for q7_item in q7_possibilities:
            num = q7_item.get("objective_number")
            if num and num in q6_map:
                merged.append({**q6_map[num], **q7_item})
            else:
                merged.append(q7_item)
        return {**q7_res, "creative_possibilities": merged}

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q7")

        state_db_path = context.get("nine_question_state_db_path")
        session_id = str(context.get("session_id") or "nq-baseline")
        q6_internal = load_q6_internal_llm_output_from_table(db_path=state_db_path, session_id=session_id)
        q6_external = load_q6_external_llm_output_from_table(db_path=state_db_path, session_id=session_id)

        internal_run = start_module_run(
            module_runs,
            "q7_internal_creativity_llm",
            source="plugins.nine_questions.q7.internal",
        )
        try:
            internal_result = self.run_internal_creative_profile(context, q6_internal)
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
            external_result = self.run_external_creative_profile(context, q6_external)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q7_external_creativity_failed", error_message=str(exc))
            raise

        internal_context_updates = build_q7_internal_context_updates(internal_result)
        external_context_updates = build_q7_external_context_updates(external_result)

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q7 internal/external creative combined with Q6 constraints by objective_number.",
            context_updates={
                **internal_context_updates,
                **external_context_updates,
                "q7_execution_diagnosis": {
                    "authenticity_status": "completed",
                    "diagnosis_code": "internal_external_llm_merged_with_q6",
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
