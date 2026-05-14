from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q9_how_should_i_act.external.llm_prompt import (
    build_q9_external_llm_request,
)
from plugins.nine_questions.q9_how_should_i_act.q8_public_context import (
    build_q9_q8_public_action_context,
    q9_public_action_context_size,
)
from plugins.nine_questions.q8_what_should_i_do_now.service import (
    load_external_public_output as load_q8_external_public_output,
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
from zentex.common.observable_logging import observable_event

logger = logging.getLogger(__name__)


def _log(event: str, **fields: Any) -> None:
    observable_event(
        logger,
        event,
        component="nine_questions.q9.external",
        question_id="q9",
        scope="external",
        **fields,
    )

_EXTERNAL_ACTION_DESIGN_FIELDS = {
    "action_objective",
    "external_steps",
    "required_external_resources",
    "verification_checks",
    "stop_conditions",
    "evidence_refs",
}
_EXTERNAL_ACTION_DESIGN_LIST_FIELDS = {
    "external_steps",
    "required_external_resources",
    "verification_checks",
    "stop_conditions",
    "evidence_refs",
}


def run_q9_external_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or context.get("request_id") or "unknown-turn")
    trace_id = f"{context.get('trace_id') or 'q9'}:external"
    request_id = f"q9-external-request:{uuid4().hex}"
    decision_id = f"q9-external:{uuid4().hex}"
    started = perf_counter()
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    upstream_context = _build_q9_external_upstream_context(context)
    _log(
        "q9_upstream_context_loaded",
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        upstream_source=upstream_context.get("q9_upstream_public_contract", {}).get("source")
        if isinstance(upstream_context.get("q9_upstream_public_contract"), dict)
        else "",
        upstream_context_size_chars=upstream_context.get("q9_upstream_public_contract", {}).get("context_size_chars")
        if isinstance(upstream_context.get("q9_upstream_public_contract"), dict)
        else None,
    )
    request = build_q9_external_llm_request(context=upstream_context)
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q9_external_action",
        question_ref="q9:external",
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
        payload={"q9_external_llm_input": llm_input},
    )
    observable_event(
        logger,
        "q9_llm_input",
        component="nine_questions.q9.external",
        question_id="q9",
        scope="external",
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        decision_id=decision_id,
        request_id=request_id,
        provider=safe_provider_plugin_id(provider),
        llm_input=llm_input,
    )
    try:
        from plugins.nine_questions.q9_how_should_i_act.external.instructor_contract import (
            generate_external_action_design_with_instructor_contract,
        )

        llm_output = generate_external_action_design_with_instructor_contract(
            provider,
            prompt=f"{request['system_prompt']}\n\n{request['prompt']}",
            context=request["model_context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q9",
                "scope": "external",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        observable_event(
            logger,
            "q9_llm_output",
            component="nine_questions.q9.external",
            question_id="q9",
            scope="external",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            decision_id=decision_id,
            request_id=request_id,
            provider=safe_provider_plugin_id(provider),
            llm_output=llm_output,
        )
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_external_action_llm",
            payload={
                "q9_external_llm_input": llm_input,
                "q9_external_llm_output": llm_output,
                "q9_external_action_design": llm_output,
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
                "q9_external_llm_output": llm_output,
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        _log(
            "q9_action_design_completed",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            decision_id=decision_id,
            request_id=request_id,
            elapsed_ms=int((perf_counter() - started) * 1000),
            token_usage=json_safe_payload(getattr(provider, "last_token_usage", None)),
            model=json_safe_payload(getattr(provider, "last_model_name", None)),
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
                "q9_external_llm_input": llm_input,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q9 EXTERNAL LLM ERROR] trace_id=%s", trace_id)
        _log(
            "q9_action_design_failed",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            decision_id=decision_id,
            request_id=request_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        raise


def _extract_external_result(llm_output: dict[str, Any]) -> dict[str, Any]:
    value = llm_output.get("Q9ExternalActionDesign")
    if not isinstance(value, dict):
        raise RuntimeError("q9_external_action_design_missing")
    actual_fields = set(value)
    if actual_fields != _EXTERNAL_ACTION_DESIGN_FIELDS:
        raise RuntimeError(
            "q9_external_action_design_schema_mismatch: "
            f"actual_fields={sorted(actual_fields)} "
            f"expected_fields={sorted(_EXTERNAL_ACTION_DESIGN_FIELDS)}"
        )
    action_objective = str(value.get("action_objective") or "").strip()
    if not action_objective:
        raise RuntimeError("q9_external_action_design_action_objective_empty")
    normalized: dict[str, Any] = {"action_objective": action_objective}
    for field in sorted(_EXTERNAL_ACTION_DESIGN_LIST_FIELDS):
        raw_items = value.get(field)
        if not isinstance(raw_items, list):
            raise RuntimeError(f"q9_external_action_design_{field}_not_list")
        items = [str(item).strip() for item in raw_items if str(item or "").strip()]
        if not items:
            raise RuntimeError(f"q9_external_action_design_{field}_empty")
        normalized[field] = items
    return {
        "action_objective": normalized["action_objective"],
        "external_steps": normalized["external_steps"],
        "required_external_resources": normalized["required_external_resources"],
        "verification_checks": normalized["verification_checks"],
        "stop_conditions": normalized["stop_conditions"],
        "evidence_refs": normalized["evidence_refs"],
    }


def _build_q9_external_upstream_context(context: dict[str, Any]) -> dict[str, Any]:
    upstream = {
        key: context[key]
        for key in ("question_id", "question_text", "trace_id", "turn_id", "request_id", "question_driver_refs")
        if context.get(key) not in (None, "", [], {})
    }
    q8_public_output = load_q8_external_public_output(
        db_path=context.get("nine_question_state_db_path"),
        session_id=str(context.get("session_id") or "nq-baseline"),
    )
    q8_action_context = build_q9_q8_public_action_context(q8_public_output, expected_scope="external")
    upstream["Q8_ExternalObjectiveProfile"] = q8_action_context
    upstream["q9_upstream_public_contract"] = {
        "source": "plugins.nine_questions.q8_what_should_i_do_now.service.load_external_public_output",
        "context_size_chars": q9_public_action_context_size(q8_action_context),
    }
    return upstream
