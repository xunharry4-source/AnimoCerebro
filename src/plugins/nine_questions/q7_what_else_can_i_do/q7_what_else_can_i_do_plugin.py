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
from plugins.nine_questions.q6_what_should_i_not_do.service import (
    load_external_public_output as load_q6_external_public_output,
    load_internal_public_output as load_q6_internal_public_output,
)
from plugins.nine_questions.q7_what_else_can_i_do.llm_output_table import (
    build_external_public_output,
    build_internal_public_output,
    save_q7_objective_llm_io_to_table,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    persist_question_module_output,
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

    def build_internal_public_output(self, q7_output: dict[str, Any], q6_public_output: dict[str, Any]) -> dict[str, Any]:
        return build_internal_public_output(q7_output=q7_output, q6_public_output=q6_public_output)

    def build_external_public_output(self, q7_output: dict[str, Any], q6_public_output: dict[str, Any]) -> dict[str, Any]:
        return build_external_public_output(q7_output=q7_output, q6_public_output=q6_public_output)

    def run_internal_creative_profile(self, context: dict[str, Any], q6_result: dict[str, Any]) -> dict[str, Any]:
        _, _, q7_output = self._run_internal_creative_batch(context, q6_result)
        return self.build_internal_public_output(q7_output, q6_result)

    def _run_internal_creative_batch(
        self,
        context: dict[str, Any],
        q6_result: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        q6_items = q6_result.get("constraints_by_objective", [])
        if not isinstance(q6_items, list) or not q6_items:
            raise RuntimeError("q7_internal_upstream_missing:q6_constraints_by_objective")

        raw_possibilities: list[dict[str, Any]] = []
        request_batch: list[dict[str, Any]] = []
        session_id = str(context.get("session_id") or "nq-baseline")
        for index, objective in enumerate(q6_items, start=1):
            if not isinstance(objective, dict):
                raise RuntimeError(f"q7_internal_objective_invalid:{index}")
            objective_number = str(objective.get("objective_number") or "").strip()
            if not objective_number:
                raise RuntimeError(f"q7_internal_objective_number_missing:{index}")
            constraint_slice = {
                "type": "InternalPlanConstraintSet",
                "constraints_by_objective": [objective],
            }
            slice_context = {
                **context,
                "q7_q6_internal_constraint_slice": constraint_slice,
                "trace_id": f"{context.get('trace_id') or 'q7'}:internal:{objective_number}",
            }
            try:
                result = run_q7_internal_llm_and_save(slice_context)
            except Exception as exc:
                raise RuntimeError(f"q7_internal_objective_failed:{objective_number}:{exc}") from exc
            request_batch.append({"objective_number": objective_number, "llm_input": result["llm_input"]})
            possibilities = result["result"].get("creative_possibilities", [])
            if not isinstance(possibilities, list) or not possibilities:
                raise RuntimeError(f"q7_internal_creative_possibilities_missing:{objective_number}")
            save_q7_objective_llm_io_to_table(
                db_path=context.get("nine_question_state_db_path"),
                session_id=session_id,
                lane="internal",
                objective_number=objective_number,
                llm_input=result["llm_input"],
                output_payload=result["llm_output"],
                creative_profile=result["result"],
            )
            raw_possibilities.extend(possibilities)

        raw_profile = {"type": "InternalCreativePossibilitySet", "creative_possibilities": raw_possibilities}
        llm_input = {"type": "Q7InternalObjectiveRequestBatch", "objective_requests": request_batch}
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_internal_creativity_llm",
            payload={
                "q7_internal_llm_input": llm_input,
                "q7_internal_llm_output": raw_profile,
            },
            status="completed",
            output_kind="inference",
            trace_id=str(context.get("trace_id") or "q7:internal"),
        )
        return raw_profile, llm_input, raw_profile

    def run_external_creative_profile(self, context: dict[str, Any], q6_result: dict[str, Any]) -> dict[str, Any]:
        _, _, q7_output = self._run_external_creative_batch(context, q6_result)
        return self.build_external_public_output(q7_output, q6_result)

    def _run_external_creative_batch(
        self,
        context: dict[str, Any],
        q6_result: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        q6_items = q6_result.get("objective_constraints", [])
        if not isinstance(q6_items, list) or not q6_items:
            raise RuntimeError("q7_external_upstream_missing:q6_objective_constraints")

        raw_possibilities: list[dict[str, Any]] = []
        request_batch: list[dict[str, Any]] = []
        session_id = str(context.get("session_id") or "nq-baseline")
        for index, objective in enumerate(q6_items, start=1):
            if not isinstance(objective, dict):
                raise RuntimeError(f"q7_external_objective_invalid:{index}")
            objective_number = str(objective.get("objective_number") or "").strip()
            if not objective_number:
                raise RuntimeError(f"q7_external_objective_number_missing:{index}")
            constraint_slice = {
                "type": "ExternalPlanConstraintSet",
                "objective_constraints": [objective],
            }
            slice_context = {
                **context,
                "q7_q6_external_constraint_slice": constraint_slice,
                "trace_id": f"{context.get('trace_id') or 'q7'}:external:{objective_number}",
            }
            try:
                result = run_q7_external_llm_and_save(slice_context)
            except Exception as exc:
                raise RuntimeError(f"q7_external_objective_failed:{objective_number}:{exc}") from exc
            request_batch.append({"objective_number": objective_number, "llm_input": result["llm_input"]})
            possibilities = result["result"].get("creative_possibilities", [])
            if not isinstance(possibilities, list) or not possibilities:
                raise RuntimeError(f"q7_external_creative_possibilities_missing:{objective_number}")
            save_q7_objective_llm_io_to_table(
                db_path=context.get("nine_question_state_db_path"),
                session_id=session_id,
                lane="external",
                objective_number=objective_number,
                llm_input=result["llm_input"],
                output_payload=result["llm_output"],
                creative_profile=result["result"],
            )
            raw_possibilities.extend(possibilities)

        raw_profile = {"type": "ExternalCreativePossibilitySet", "creative_possibilities": raw_possibilities}
        llm_input = {"type": "Q7ExternalObjectiveRequestBatch", "objective_requests": request_batch}
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_external_creativity_llm",
            payload={
                "q7_external_llm_input": llm_input,
                "q7_external_llm_output": raw_profile,
            },
            status="completed",
            output_kind="inference",
            trace_id=str(context.get("trace_id") or "q7:external"),
        )
        return raw_profile, llm_input, raw_profile

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q7")

        state_db_path = context.get("nine_question_state_db_path")
        session_id = str(context.get("session_id") or "nq-baseline")
        q6_internal = load_q6_internal_public_output(db_path=state_db_path, session_id=session_id)
        q6_external = load_q6_external_public_output(db_path=state_db_path, session_id=session_id)

        internal_run = start_module_run(
            module_runs,
            "q7_internal_creativity_llm",
            source="plugins.nine_questions.q7.internal",
        )
        try:
            _, _, q7_internal_output = self._run_internal_creative_batch(context, q6_internal)
            internal_result = self.build_internal_public_output(q7_internal_output, q6_internal)
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
            _, _, q7_external_output = self._run_external_creative_batch(context, q6_external)
            external_result = self.build_external_public_output(q7_external_output, q6_external)
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
