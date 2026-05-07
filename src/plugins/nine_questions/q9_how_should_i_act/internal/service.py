from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q9_how_should_i_act.internal.llm_prompt import (
    build_q9_internal_llm_request,
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

_INTERNAL_ACTION_DESIGN_FIELDS = {
    "action_objective",
    "internal_steps",
    "required_internal_resources",
    "verification_checks",
    "stop_conditions",
    "evidence_refs",
}
_INTERNAL_ACTION_DESIGN_LIST_FIELDS = {
    "internal_steps",
    "required_internal_resources",
    "verification_checks",
    "stop_conditions",
    "evidence_refs",
}


def run_q9_internal_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or context.get("request_id") or "unknown-turn")
    trace_id = f"{context.get('trace_id') or 'q9'}:internal"
    request_id = f"q9-internal-request:{uuid4().hex}"
    decision_id = f"q9-internal:{uuid4().hex}"
    started = perf_counter()
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    request = build_q9_internal_llm_request(context=dict(context))
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q9_internal_action",
        question_ref="q9:internal",
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
    record_model_invoked(
        transcript_store,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source=__name__,
        payload={"q9_internal_llm_input": llm_input},
    )
    logger.info("[Q9 INTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    try:
        raw_output = provider.generate_json(
            prompt=f"{request['system_prompt']}\n\n{request['prompt']}",
            context=request["model_context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q9",
                "scope": "internal",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        llm_output = raw_output if isinstance(raw_output, dict) else {}
        if not llm_output:
            raise RuntimeError("q9_internal_llm_output_empty")
        logger.info("[Q9 INTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_internal_action_llm",
            payload={
                "q9_internal_llm_input": llm_input,
                "q9_internal_llm_output": llm_output,
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
                "q9_internal_llm_output": llm_output,
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        return {
            "llm_input": llm_input,
            "llm_output": llm_output,
            "result": _extract_internal_result(llm_output),
        }
    except Exception as exc:
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q9_internal_llm_input": llm_input,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q9 INTERNAL LLM ERROR] trace_id=%s", trace_id)
        raise


def _extract_internal_result(llm_output: dict[str, Any]) -> dict[str, Any]:
    value = llm_output.get("Q9InternalActionDesign")
    if not isinstance(value, dict):
        raise RuntimeError("q9_internal_action_design_missing")
    actual_fields = set(value)
    if actual_fields != _INTERNAL_ACTION_DESIGN_FIELDS:
        raise RuntimeError(
            "q9_internal_action_design_schema_mismatch: "
            f"actual_fields={sorted(actual_fields)} "
            f"expected_fields={sorted(_INTERNAL_ACTION_DESIGN_FIELDS)}"
        )
    action_objective = str(value.get("action_objective") or "").strip()
    if not action_objective:
        raise RuntimeError("q9_internal_action_design_action_objective_empty")
    normalized: dict[str, Any] = {"action_objective": action_objective}
    for field in sorted(_INTERNAL_ACTION_DESIGN_LIST_FIELDS):
        raw_items = value.get(field)
        if not isinstance(raw_items, list):
            raise RuntimeError(f"q9_internal_action_design_{field}_not_list")
        items = [str(item).strip() for item in raw_items if str(item or "").strip()]
        if not items:
            raise RuntimeError(f"q9_internal_action_design_{field}_empty")
        normalized[field] = items
    return {
        "action_objective": normalized["action_objective"],
        "internal_steps": normalized["internal_steps"],
        "required_internal_resources": normalized["required_internal_resources"],
        "verification_checks": normalized["verification_checks"],
        "stop_conditions": normalized["stop_conditions"],
        "evidence_refs": normalized["evidence_refs"],
    }
