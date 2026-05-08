from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q7_what_else_can_i_do.internal.llm_prompt import (
    build_q7_internal_llm_request,
)
from plugins.nine_questions.q6_what_should_i_not_do.llm_output_table import (
    load_internal_llm_output_from_table as load_q6_internal_llm_output_from_table,
)
from plugins.nine_questions.q7_what_else_can_i_do.assessment_contract import (
    normalize_q7_internal_creative_possibility_set,
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


def run_q7_internal_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or context.get("request_id") or "unknown-turn")
    trace_id = f"{context.get('trace_id') or 'q7'}:internal"
    request_id = f"q7-internal-request:{uuid4().hex}"
    decision_id = f"q7-internal:{uuid4().hex}"
    started = perf_counter()
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    request = build_q7_internal_llm_request(context=_build_q7_internal_upstream_context(context))
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q7_internal_creativity",
        question_ref="q7:internal",
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
    logger.info("[Q7 INTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    record_model_invoked(
        transcript_store,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source=__name__,
        payload={"q7_internal_llm_input": llm_input},
    )
    try:
        from plugins.nine_questions.q7_what_else_can_i_do.internal.instructor_contract import (
            generate_internal_creative_possibility_set_with_instructor_contract,
        )

        llm_output = generate_internal_creative_possibility_set_with_instructor_contract(
            provider,
            prompt=f"{request['system_prompt']}\n\n{request['prompt']}",
            context=request["model_context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q7",
                "scope": "internal",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        logger.info("[Q7 INTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
        persist_question_module_output(
            context,
            question_id="q7",
            module_id="q7_internal_creativity_llm",
            payload={
                "q7_internal_llm_input": llm_input,
                "q7_internal_llm_output": llm_output,
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
                "q7_internal_llm_output": llm_output,
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        return {
            "llm_input": llm_input,
            "llm_output": llm_output,
            "result": llm_output,
        }
    except Exception as exc:
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q7_internal_llm_input": llm_input,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q7 INTERNAL LLM ERROR] trace_id=%s", trace_id)
        raise


def _extract_internal_result(llm_output: dict[str, Any]) -> dict[str, Any]:
    return normalize_q7_internal_creative_possibility_set(llm_output)


def _build_q7_internal_upstream_context(context: dict[str, Any]) -> dict[str, Any]:
    upstream = {
        key: context[key]
        for key in ("question_id", "question_text", "trace_id", "turn_id", "request_id", "question_driver_refs")
        if context.get(key) not in (None, "", [], {})
    }
    upstream["Q6_InternalPlanConstraintSet"] = load_q6_internal_llm_output_from_table(
        db_path=context.get("nine_question_state_db_path"),
        session_id=str(context.get("session_id") or "nq-baseline"),
    )
    return upstream
