from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q5_what_am_i_allowed_to_do.boundary_projection import (
    normalize_q5_external_boundary,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.external.llm_prompt import (
    build_q5_external_llm_request,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_flow import (
    persist_q5_model_completed,
    persist_q5_model_invoked,
)
from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    persist_question_module_output,
    record_model_failed,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)


def run_q5_external_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or context.get("request_id") or "unknown-turn")
    trace_id = f"{context.get('trace_id') or 'q5'}:external"
    request_id = f"q5-external-request:{uuid4().hex}"
    decision_id = f"q5-external:{uuid4().hex}"
    started = perf_counter()
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    request = build_q5_external_llm_request(context=dict(context))
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q5_external_authorization",
        question_ref="q5:external",
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
    persist_q5_model_invoked(
        transcript_store,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source=__name__,
        payload={"q5_external_llm_input": llm_input},
    )
    logger.info("[Q5 EXTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    try:
        raw_output = provider.generate_json(
            prompt=f"{request['system_prompt']}\n\n{request['prompt']}",
            context=request["model_context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q5",
                "scope": "external",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        llm_output = raw_output if isinstance(raw_output, dict) else {}
        if not llm_output:
            raise RuntimeError("q5_external_llm_output_empty")
        result = normalize_q5_external_boundary(llm_output)
        persist_question_module_output(
            context,
            question_id="q5",
            module_id="q5_external_authorization_llm",
            payload={
                "q5_external_llm_input": llm_input,
                "q5_external_llm_output": llm_output,
            },
            status="completed",
            output_kind="inference",
            trace_id=trace_id,
        )
        persist_q5_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q5_external_llm_output": llm_output,
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        logger.info("[Q5 EXTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
        return {
            "llm_input": llm_input,
            "llm_output": llm_output,
            "result": result,
        }
    except Exception as exc:
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q5_external_llm_input": llm_input,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q5 EXTERNAL LLM ERROR] trace_id=%s", trace_id)
        raise
