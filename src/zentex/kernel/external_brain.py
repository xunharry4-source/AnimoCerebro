from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType
from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType

UTC = timezone.utc

REQUIRED_QUESTIONS = tuple(f"q{i}" for i in range(1, 10))


def consult_external_brain(
    *,
    session_id: str,
    user_input: str,
    context: dict[str, Any] | None,
    llm_service: Any,
    transcript_store: Any,
    nine_question_state: dict[str, Any] | None,
    system_identity: dict[str, Any] | None,
    turn_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    if not str(session_id or "").strip():
        raise ValueError("session_id is required for G1 external brain consultation")
    if not str(user_input or "").strip():
        raise ValueError("user_input is required for G1 external brain consultation")
    if llm_service is None or not callable(getattr(llm_service, "generate_json", None)):
        raise RuntimeError("G1 requires a live LLM service; refusing rule-engine fallback")

    resolved_turn_id = turn_id or str(uuid4())
    resolved_trace_id = trace_id or f"g1-external-brain:{session_id}:{resolved_turn_id}"
    request_context = _normalize_context(context)

    _write_transcript(
        transcript_store,
        session_id=session_id,
        turn_id=resolved_turn_id,
        trace_id=resolved_trace_id,
        event="g1_bridge_request_received",
        payload={
            "user_input": user_input,
            "input_channels": sorted(request_context.keys()),
            "host_retains_final_execution": True,
        },
    )

    llm_result = llm_service.generate_json(
        prompt=_external_brain_prompt(),
        context={
            "user_input": user_input,
            "workspace_state": request_context.get("workspace_state", {}),
            "host_context": request_context.get("host_context", {}),
            "external_signals": request_context.get("external_signals", []),
            "long_term_memory": request_context.get("long_term_memory", []),
            "nine_question_state": nine_question_state or {},
            "system_identity": system_identity or {},
            "g1_rules": {
                "zentex_is_external_brain": True,
                "host_retains_final_execution": True,
                "zentex_must_not_execute": True,
                "live_llm_required": True,
            },
        },
        caller_context=ModelProviderCallerContext(
            source_module="kernel.g1_external_brain",
            invocation_phase="g1_consultation",
            question_driver_refs=list(REQUIRED_QUESTIONS),
            decision_id=resolved_trace_id,
            trace_id=resolved_trace_id,
        ),
        source_module="kernel.g1_external_brain",
        invocation_phase="g1_consultation",
        decision_id=resolved_trace_id,
        temperature=0.1,
        max_output_tokens=1600,
        metadata={
            "feature_code": "G1",
            "requires_live_llm": True,
            "question_driver_refs": list(REQUIRED_QUESTIONS),
        },
    )
    llm_output = getattr(llm_result, "output", None)
    if not isinstance(llm_output, dict):
        raise RuntimeError("G1 live LLM returned no structured JSON output")

    advice = _validate_and_shape_llm_output(llm_output)
    usage = getattr(llm_result, "usage", None)

    _write_transcript(
        transcript_store,
        session_id=session_id,
        turn_id=resolved_turn_id,
        trace_id=resolved_trace_id,
        event="g1_live_llm_semantic_fill_completed",
        payload={
            "provider_key": str(getattr(llm_result, "provider_key", "") or ""),
            "model": str(getattr(llm_result, "model", "") or ""),
            "usage": _usage_payload(usage),
            "question_count": len(advice["nine_question_analysis"]),
        },
    )

    result = {
        "feature_code": "G1",
        "session_id": session_id,
        "turn_id": resolved_turn_id,
        "trace_id": resolved_trace_id,
        "role": "external_brain",
        "host_retains_final_execution": True,
        "zentex_will_not_execute": True,
        "live_llm_used": True,
        "task_judgment": advice["task_judgment"],
        "decision_advice": advice["decision_advice"],
        "nine_question_analysis": advice["nine_question_analysis"],
        "audit": {
            "transcript_written": True,
            "transcript_store": transcript_store.__class__.__name__ if transcript_store is not None else "",
            "llm_provider_key": str(getattr(llm_result, "provider_key", "") or ""),
            "llm_model": str(getattr(llm_result, "model", "") or ""),
            "llm_usage": _usage_payload(usage),
        },
        "created_at": datetime.now(UTC).isoformat(),
    }

    _write_transcript(
        transcript_store,
        session_id=session_id,
        turn_id=resolved_turn_id,
        trace_id=resolved_trace_id,
        event="g1_advice_returned_to_host",
        payload={
            "task_judgment": result["task_judgment"],
            "decision_advice": result["decision_advice"],
            "host_retains_final_execution": True,
            "zentex_will_not_execute": True,
        },
    )
    return result


def _normalize_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if context is None:
        return {}
    if not isinstance(context, dict):
        raise ValueError("context must be a JSON object")
    return dict(context)


def _external_brain_prompt() -> str:
    return (
        "You are Zentex/AnimoCerebro acting only as an external brain layer. "
        "Analyze the host request through the nine-question framework and return advice only. "
        "Do not claim execution, do not write final host-facing prose, and do not invent tool results. "
        "Return exactly one JSON object with keys: task_judgment, decision_advice, nine_question_analysis. "
        "nine_question_analysis must contain q1 through q9. "
        "task_judgment must include summary, should_execute, risk_level, confidence. "
        "decision_advice must include recommendation, next_steps, boundaries, host_execution_owner, zentex_role, "
        "host_retains_final_execution, zentex_will_not_execute."
    )


def _validate_and_shape_llm_output(output: dict[str, Any]) -> dict[str, Any]:
    task_judgment = output.get("task_judgment")
    decision_advice = output.get("decision_advice")
    nine_question_analysis = output.get("nine_question_analysis")
    if not isinstance(task_judgment, dict):
        raise RuntimeError("G1 LLM output missing task_judgment object")
    if not isinstance(decision_advice, dict):
        raise RuntimeError("G1 LLM output missing decision_advice object")
    if not isinstance(nine_question_analysis, dict):
        raise RuntimeError("G1 LLM output missing nine_question_analysis object")

    nine_question_analysis = _normalize_nine_question_analysis(nine_question_analysis)
    missing_questions = [q for q in REQUIRED_QUESTIONS if q not in nine_question_analysis]
    if missing_questions:
        raise RuntimeError(f"G1 LLM output missing nine-question keys: {missing_questions}")
    decision_advice = {
        **decision_advice,
        "next_steps": _as_list(decision_advice.get("next_steps")),
        "boundaries": _as_list(decision_advice.get("boundaries")),
        "host_execution_owner": "host_agent",
        "zentex_role": "external_brain_advisor",
        "host_retains_final_execution": True,
        "zentex_will_not_execute": True,
    }
    return {
        "task_judgment": task_judgment,
        "decision_advice": decision_advice,
        "nine_question_analysis": {
            question_id: _question_payload(question_id, nine_question_analysis[question_id])
            for question_id in REQUIRED_QUESTIONS
        },
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_nine_question_analysis(value: Any) -> dict[str, Any]:
    """Normalize common live-LLM nine-question shapes without inventing answers."""
    if isinstance(value, list):
        return _normalize_question_list(value)
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, Any] = {}
    for key, item in value.items():
        question_id = _question_id_from_key(key)
        if question_id:
            normalized[question_id] = item

    if all(question_id in normalized for question_id in REQUIRED_QUESTIONS):
        return normalized

    for nested_key in (
        "questions",
        "answers",
        "analysis",
        "items",
        "nine_questions",
        "nine_question_answers",
        "nine_question_items",
    ):
        nested = value.get(nested_key)
        nested_normalized = _normalize_nine_question_analysis(nested)
        if nested_normalized:
            normalized.update({k: v for k, v in nested_normalized.items() if k not in normalized})

    return normalized


def _normalize_question_list(items: list[Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for index, item in enumerate(items, start=1):
        question_id = None
        if isinstance(item, dict):
            for key in ("question_id", "question_key", "id", "key", "number", "index", "question_number"):
                question_id = _question_id_from_key(item.get(key))
                if question_id:
                    break
        if question_id is None and len(items) == len(REQUIRED_QUESTIONS):
            question_id = f"q{index}"
        if question_id:
            normalized[question_id] = item
    return normalized


def _question_id_from_key(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in REQUIRED_QUESTIONS:
        return text
    if text.isdigit() and 1 <= int(text) <= len(REQUIRED_QUESTIONS):
        return f"q{text}"
    match = re.search(r"(?:^|[^a-z0-9])q(?:uestion)?[_\-\s]*([1-9])(?:$|[^0-9])", text)
    if match:
        return f"q{match.group(1)}"
    match = re.search(r"(?:question|问题|第)\s*([1-9])", text)
    if match:
        return f"q{match.group(1)}"
    return None


def _question_payload(question_id: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if str(value.get("answer") or value.get("summary") or "").strip():
            return value
        return {**value, "answer": str(value)}
    answer = str(value or "").strip()
    if not answer:
        raise RuntimeError(f"G1 LLM output question {question_id} has an empty answer")
    return {"answer": answer}


def _usage_payload(usage: Any) -> dict[str, int]:
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _write_transcript(
    transcript_store: Any,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    event: str,
    payload: dict[str, Any],
) -> None:
    if transcript_store is None:
        raise RuntimeError("G1 requires a transcript store; refusing unaudited consultation")
    entry_payload = {
        "feature_code": "G1",
        "entry_type": event,
        "trace_id": trace_id,
        **_json_safe(payload),
    }
    if callable(getattr(transcript_store, "write_entry", None)):
        transcript_store.write_entry(
            session_id=session_id,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.DECISION_SYNTHESIZED,
            trace_id=trace_id,
            source="kernel.g1_external_brain",
            payload=entry_payload,
        )
        return
    if callable(getattr(transcript_store, "append", None)):
        transcript_store.append(
            TranscriptEntry(
                entry_type=TranscriptEntryType.decision_synthesized,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="kernel.g1_external_brain",
                payload=entry_payload,
            )
        )
        return
    raise RuntimeError("G1 transcript store does not support write_entry or append")


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
