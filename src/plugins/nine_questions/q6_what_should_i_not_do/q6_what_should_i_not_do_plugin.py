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
from plugins.nine_questions.q5_what_am_i_allowed_to_do.service import (
    load_public_output as load_q5_public_output,
)
from plugins.nine_questions.q6_what_should_i_not_do.llm_output_table import (
    build_external_public_output,
    build_internal_public_output,
    save_q6_objective_llm_io_to_table,
    save_q6_llm_io_to_table,
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

    def build_internal_public_output(self, q6_llm_output: dict[str, Any], q5_public_output: dict[str, Any]) -> dict[str, Any]:
        return build_internal_public_output(q6_llm_output=q6_llm_output, q5_public_output=q5_public_output)

    def build_external_public_output(self, q6_llm_output: dict[str, Any], q5_public_output: dict[str, Any]) -> dict[str, Any]:
        return build_external_public_output(q6_llm_output=q6_llm_output, q5_public_output=q5_public_output)

    def run_internal_consequence_profile(self, context: dict[str, Any], q5_result: dict[str, Any]) -> dict[str, Any]:
        _, _, q6_llm_output = self._run_internal_consequence_batch(context, q5_result)
        return self.build_internal_public_output(q6_llm_output, q5_result)

    def _run_internal_consequence_batch(
        self,
        context: dict[str, Any],
        q5_result: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        q5_allowed = q5_result.get("allowed_internal_objectives_with_conditions", [])
        if not isinstance(q5_allowed, list) or not q5_allowed:
            raise RuntimeError("q6_internal_upstream_missing:q5_allowed_internal_objectives")

        raw_constraints: list[dict[str, Any]] = []
        request_batch: list[dict[str, Any]] = []
        for index, objective in enumerate(q5_allowed, start=1):
            if not isinstance(objective, dict):
                raise RuntimeError(f"q6_internal_objective_invalid:{index}")
            objective_number = str(objective.get("objective_number") or "").strip()
            if not objective_number:
                raise RuntimeError(f"q6_internal_objective_number_missing:{index}")
            slice_context = {
                **context,
                "q6_q5_internal_objective_slice": [objective],
                "trace_id": f"{context.get('trace_id') or 'q6'}:internal:{objective_number}",
            }
            try:
                result = run_q6_internal_llm_and_save(slice_context)
            except Exception as exc:
                raise RuntimeError(f"q6_internal_objective_failed:{objective_number}:{exc}") from exc
            request_batch.append({"objective_number": objective_number, "llm_input": result["llm_input"]})
            q6_constraints = result["result"].get("constraints_by_objective", [])
            if not isinstance(q6_constraints, list) or not q6_constraints:
                raise RuntimeError(f"q6_internal_objective_constraints_missing:{objective_number}")
            save_q6_objective_llm_io_to_table(
                db_path=context.get("nine_question_state_db_path"),
                session_id=str(context.get("session_id") or "nq-baseline"),
                lane="internal",
                objective_number=objective_number,
                llm_input=result["llm_input"],
                llm_output=result["llm_output"],
                consequence_profile=result["result"],
            )
            raw_constraints.extend(q6_constraints)

        raw_profile = {"type": "InternalPlanConstraintSet", "constraints_by_objective": raw_constraints}
        llm_input = {"type": "Q6InternalObjectiveRequestBatch", "objective_requests": request_batch}
        llm_output = raw_profile
        save_q6_llm_io_to_table(
            db_path=context.get("nine_question_state_db_path"),
            session_id=str(context.get("session_id") or "nq-baseline"),
            llm_input_field="q6_internal_llm_input",
            llm_input=llm_input,
            llm_output_field="q6_internal_llm_output",
            llm_output=llm_output,
        )
        return raw_profile, llm_input, llm_output

    def run_external_consequence_profile(self, context: dict[str, Any], q5_result: dict[str, Any]) -> dict[str, Any]:
        _, _, q6_llm_output = self._run_external_consequence_batch(context, q5_result)
        return self.build_external_public_output(q6_llm_output, q5_result)

    def _run_external_consequence_batch(
        self,
        context: dict[str, Any],
        q5_result: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        q5_allowed = q5_result.get("allowed_external_objectives_with_conditions", [])
        if not isinstance(q5_allowed, list) or not q5_allowed:
            raise RuntimeError("q6_external_upstream_missing:q5_allowed_external_objectives")

        raw_constraints: list[dict[str, Any]] = []
        request_batch: list[dict[str, Any]] = []
        for index, objective in enumerate(q5_allowed, start=1):
            if not isinstance(objective, dict):
                raise RuntimeError(f"q6_external_objective_invalid:{index}")
            objective_number = str(objective.get("objective_number") or "").strip()
            if not objective_number:
                raise RuntimeError(f"q6_external_objective_number_missing:{index}")
            slice_context = {
                **context,
                "q6_q5_external_objective_slice": [objective],
                "trace_id": f"{context.get('trace_id') or 'q6'}:external:{objective_number}",
            }
            try:
                result = run_q6_external_llm_and_save(slice_context)
            except Exception as exc:
                raise RuntimeError(f"q6_external_objective_failed:{objective_number}:{exc}") from exc
            request_batch.append({"objective_number": objective_number, "llm_input": result["llm_input"]})
            q6_constraints = result["result"].get("objective_constraints", [])
            if not isinstance(q6_constraints, list) or not q6_constraints:
                raise RuntimeError(f"q6_external_objective_constraints_missing:{objective_number}")
            save_q6_objective_llm_io_to_table(
                db_path=context.get("nine_question_state_db_path"),
                session_id=str(context.get("session_id") or "nq-baseline"),
                lane="external",
                objective_number=objective_number,
                llm_input=result["llm_input"],
                llm_output=result["llm_output"],
                consequence_profile=result["result"],
            )
            raw_constraints.extend(q6_constraints)

        raw_profile = {"type": "ExternalPlanConstraintSet", "objective_constraints": raw_constraints}
        llm_input = {"type": "Q6ExternalObjectiveRequestBatch", "objective_requests": request_batch}
        llm_output = raw_profile
        save_q6_llm_io_to_table(
            db_path=context.get("nine_question_state_db_path"),
            session_id=str(context.get("session_id") or "nq-baseline"),
            llm_input_field="q6_external_llm_input",
            llm_input=llm_input,
            llm_output_field="q6_external_llm_output",
            llm_output=llm_output,
        )
        return raw_profile, llm_input, llm_output

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q6")

        state_db_path = context.get("nine_question_state_db_path")
        session_id = str(context.get("session_id") or "nq-baseline")
        q5_public_output = load_q5_public_output(db_path=state_db_path, session_id=session_id)
        q5_internal = q5_public_output["q5_internal_authorization_boundary"]
        q5_external = q5_public_output["q5_external_authorization_boundary"]

        internal_run = start_module_run(
            module_runs,
            "q6_internal_consequence_llm",
            source="plugins.nine_questions.q6.internal",
        )
        try:
            _, q6_internal_llm_input, q6_internal_llm_output = self._run_internal_consequence_batch(
                context,
                q5_internal,
            )
            internal_profile = self.build_internal_public_output(q6_internal_llm_output, q5_internal)
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
            _, q6_external_llm_input, q6_external_llm_output = self._run_external_consequence_batch(
                context,
                q5_external,
            )
            external_profile = self.build_external_public_output(q6_external_llm_output, q5_external)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q6_external_consequence_failed", error_message=str(exc))
            raise

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q6 internal/external consequence combined with Q5 authorization by objective_number.",
            llm_output={
                "q6_internal_llm_input": q6_internal_llm_input,
                "q6_internal_llm_output": q6_internal_llm_output,
                "q6_external_llm_input": q6_external_llm_input,
                "q6_external_llm_output": q6_external_llm_output,
                "q6_internal_consequence_profile": internal_profile,
                "q6_external_consequence_profile": external_profile,
            },
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
