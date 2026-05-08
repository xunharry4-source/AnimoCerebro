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
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_output_table import (
    load_external_llm_output_from_table as load_q5_external_llm_output_from_table,
    load_internal_llm_output_from_table as load_q5_internal_llm_output_from_table,
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

    def run_internal_consequence_profile(self, context: dict[str, Any], q5_result: dict[str, Any]) -> dict[str, Any]:
        q6_res = run_q6_internal_llm_and_save(context)["result"]
        q5_allowed = q5_result.get("allowed_internal_objectives_with_conditions", [])
        if not isinstance(q5_allowed, list):
            return q6_res

        q5_map = {item.get("objective_number"): item for item in q5_allowed if item.get("objective_number")}
        q6_constraints = q6_res.get("constraints_by_objective", [])
        if not isinstance(q6_constraints, list):
            return q6_res

        merged = []
        for q6_item in q6_constraints:
            num = q6_item.get("objective_number")
            if num and num in q5_map:
                merged.append({**q5_map[num], **q6_item})
            else:
                merged.append(q6_item)
        return {**q6_res, "constraints_by_objective": merged}

    def run_external_consequence_profile(self, context: dict[str, Any], q5_result: dict[str, Any]) -> dict[str, Any]:
        q6_res = run_q6_external_llm_and_save(context)["result"]
        q5_allowed = q5_result.get("allowed_external_objectives_with_conditions", [])
        if not isinstance(q5_allowed, list):
            return q6_res

        q5_map = {item.get("objective_number"): item for item in q5_allowed if item.get("objective_number")}
        q6_constraints = q6_res.get("objective_constraints", [])
        if not isinstance(q6_constraints, list):
            return q6_res

        merged = []
        for q6_item in q6_constraints:
            num = q6_item.get("objective_number")
            if num and num in q5_map:
                merged.append({**q5_map[num], **q6_item})
            else:
                merged.append(q6_item)
        return {**q6_res, "objective_constraints": merged}

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q6")

        state_db_path = context.get("nine_question_state_db_path")
        session_id = str(context.get("session_id") or "nq-baseline")
        q5_internal = load_q5_internal_llm_output_from_table(db_path=state_db_path, session_id=session_id)
        q5_external = load_q5_external_llm_output_from_table(db_path=state_db_path, session_id=session_id)

        internal_run = start_module_run(
            module_runs,
            "q6_internal_consequence_llm",
            source="plugins.nine_questions.q6.internal",
        )
        try:
            internal_profile = self.run_internal_consequence_profile(context, q5_internal)
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
            external_profile = self.run_external_consequence_profile(context, q5_external)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q6_external_consequence_failed", error_message=str(exc))
            raise

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q6 internal/external consequence combined with Q5 authorization by objective_number.",
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
                    "diagnosis_code": "internal_external_llm_merged_with_q5",
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
