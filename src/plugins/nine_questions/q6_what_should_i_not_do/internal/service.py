from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q6_what_should_i_not_do.internal.llm_prompt import (
    build_q6_internal_llm_request,
)
from plugins.nine_questions.q6_what_should_i_not_do.llm_output_table import (
    save_q6_llm_io_to_table,
)
from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)

_Q6_INTERNAL_ROOT_KEY = "InternalPlanConstraintSet"
_REQUIRED_CONSTRAINT_TEXT_FIELDS = (
    "objective_reference",
    "cognitive_cost",
    "memory_impact",
    "reflection_overuse_risk",
    "learning_overfit_risk",
    "value_drift_risk",
    "strategy_pollution_risk",
    "self_evolution_failure_modes",
    "sandbox_requirements",
    "verification_requirements",
    "pause_conditions",
    "stop_conditions",
    "rollback_requirements",
)
_EMPTY_SAFEGUARD_VALUES = {"无", "不需要", "无需", "暂无", "n/a", "none", "not required"}
_PLAN_STEP_MARKERS = (
    "task_id",
    "subtask_id",
    "资源锁",
    "步骤",
    "第一步",
    "执行步骤",
    "实现计划",
    "任务拆解",
    "流程图",
    "建单",
    "resource_lock",
)


def run_q6_internal_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or context.get("request_id") or "unknown-turn")
    trace_id = f"{context.get('trace_id') or 'q6'}:internal"
    request_id = f"q6-internal-request:{uuid4().hex}"
    decision_id = f"q6-internal:{uuid4().hex}"
    started = perf_counter()
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    request = build_q6_internal_llm_request(context=dict(context))
    _require_q5_allowed_internal_objectives(request)
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q6_internal_consequence",
        question_ref="q6:internal",
        question_driver_refs=context.get("question_driver_refs"),
        decision_id=decision_id,
        trace_id=trace_id,
    )
    llm_input = {
        "request_id": request_id,
        "decision_id": decision_id,
        "provider_plugin_id": safe_provider_plugin_id(provider),
        "system_prompt": request["system_prompt"],
        "prompt": request["prompt"],
        "context": request["model_context"],
        "caller_context": caller_context.model_dump(mode="json"),
    }
    save_q6_llm_io_to_table(
        db_path=context.get("nine_question_state_db_path"),
        session_id=session_id,
        llm_input_field="q6_internal_llm_input",
        llm_input=llm_input,
        llm_output_field="q6_internal_llm_output",
        llm_output=None,
    )
    logger.info("[Q6 INTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    record_model_invoked(
        transcript_store,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source=__name__,
        payload={"q6_internal_llm_input": llm_input},
    )
    persist_question_module_output(
        context,
        question_id="q6",
        module_id="q6_internal_llm_request",
        payload={"q6_internal_llm_input": llm_input},
        status="ready",
        output_kind="llm_request",
        rollback_available=False,
        retry_available=True,
        trace_id=trace_id,
    )
    try:
        from plugins.nine_questions.q6_what_should_i_not_do.internal.instructor_contract import (
            generate_internal_plan_constraint_set_with_instructor_contract,
        )

        llm_output = generate_internal_plan_constraint_set_with_instructor_contract(
            provider,
            prompt=f"{request['system_prompt']}\n\n{request['prompt']}",
            context=request["model_context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q6",
                "scope": "internal",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
            expected_objective_numbers=_extract_expected_objective_numbers(
                request["model_context"]["context"].get("Q5_AllowedInternalObjectives")
            ),
        )
        internal_result = _extract_internal_result(llm_output)
        save_q6_llm_io_to_table(
            db_path=context.get("nine_question_state_db_path"),
            session_id=session_id,
            llm_input_field="q6_internal_llm_input",
            llm_input=llm_input,
            llm_output_field="q6_internal_llm_output",
            llm_output=llm_output,
        )
        logger.info("[Q6 INTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_internal_consequence_llm",
            payload={
                "q6_internal_llm_output": llm_output,
                "q6_internal_consequence_profile": internal_result,
            },
            status="completed",
            output_kind="inference",
            trace_id=trace_id,
        )
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q6_internal_llm_output": llm_output,
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        return {
            "llm_input": llm_input,
            "llm_output": llm_output,
            "result": internal_result,
        }
    except Exception as exc:
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q6_internal_llm_input": llm_input,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q6 INTERNAL LLM ERROR] trace_id=%s", trace_id)
        raise


def _extract_internal_result(llm_output: dict[str, Any]) -> dict[str, Any]:
    if llm_output.get("type") != _Q6_INTERNAL_ROOT_KEY:
        raise RuntimeError(f"q6_internal_result_missing_root:{_Q6_INTERNAL_ROOT_KEY}")

    constraints = llm_output.get("constraints_by_objective")
    if not isinstance(constraints, list):
        raise RuntimeError("q6_internal_result_invalid:constraints_by_objective")
    if not constraints:
        raise RuntimeError("q6_internal_result_empty:constraints_by_objective")

    normalized_constraints = [_normalize_constraint(item) for item in constraints]
    return {
        "type": _Q6_INTERNAL_ROOT_KEY,
        "constraints_by_objective": normalized_constraints,
    }


def _extract_expected_objective_numbers(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [
        str(item.get("objective_number") or "").strip()
        for item in values
        if isinstance(item, dict) and str(item.get("objective_number") or "").strip()
    ]


def _require_q5_allowed_internal_objectives(request: dict[str, Any]) -> None:
    model_context = request.get("model_context")
    prompt_context = model_context.get("context") if isinstance(model_context, dict) else None
    objectives = prompt_context.get("Q5_AllowedInternalObjectives") if isinstance(prompt_context, dict) else None
    if not isinstance(objectives, list) or not objectives:
        raise RuntimeError("q6_internal_upstream_missing:q5_allowed_internal_objectives")


def _normalize_constraint(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("q6_internal_result_invalid:constraint")
    normalized = {
        key: _require_non_empty_text(value, key)
        for key in _REQUIRED_CONSTRAINT_TEXT_FIELDS
    }
    for key in ("pause_conditions", "stop_conditions", "rollback_requirements"):
        _reject_empty_safeguard(normalized[key], key)
    normalized["must_avoid"] = _require_must_avoid(value)
    return normalized


def _require_non_empty_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"q6_internal_result_invalid:{key}")
    text = value.strip()
    _reject_plan_step_text(text, key)
    return text


def _reject_empty_safeguard(value: str, key: str) -> None:
    normalized = value.strip().lower()
    if len(value.strip()) < 5 or normalized in _EMPTY_SAFEGUARD_VALUES:
        raise RuntimeError(f"q6_internal_result_empty_safeguard:{key}")


def _require_must_avoid(payload: dict[str, Any]) -> list[str]:
    value = payload.get("must_avoid")
    if not isinstance(value, list):
        raise RuntimeError("q6_internal_result_invalid:must_avoid")
    items = [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]
    if not 1 <= len(items) <= 3:
        raise RuntimeError("q6_internal_result_invalid:must_avoid_count")
    for item in items:
        _reject_plan_step_text(item, "must_avoid")
    return items


def _reject_plan_step_text(value: str, key: str) -> None:
    normalized = value.strip().lower()
    if any(marker.lower() in normalized for marker in _PLAN_STEP_MARKERS):
        raise RuntimeError(f"q6_internal_result_contains_plan_step:{key}")
