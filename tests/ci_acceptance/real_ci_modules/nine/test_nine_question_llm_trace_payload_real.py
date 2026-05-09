from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _insert_model_trace_events(
    app: FastAPI,
    *,
    question_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """Insert real transcript rows through the app's transcript store API."""
    transcript_store = app.state.transcript_store
    session_id = app.state.session.session_id
    turn_id = app.state.session.last_turn_id
    source = f"acceptance.real_trace.{question_id}"
    request_id = f"real-trace-request-{question_id}"
    decision_id = f"real-trace-decision-{question_id}"
    prompt = f"REAL TRACE PROMPT for {question_id}"
    system_prompt = "REAL TRACE SYSTEM PROMPT"
    context = {
        "question_id": question_id,
        "source": "real_acceptance_transcript_insert",
        "expected_trace_id": trace_id,
    }
    raw_response = {
        "answer": f"real trace response for {question_id}",
        "confidence": 0.91,
    }
    caller_context = {
        "source_module": source,
        "invocation_phase": f"nine_question_{question_id}_real_trace",
        "decision_id": decision_id,
        "trace_id": trace_id,
        "question_driver_refs": [question_id],
    }

    transcript_store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type="model_provider_invoked",
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload={
            "request_id": request_id,
            "decision_id": decision_id,
            "provider_plugin_id": "ollama",
            "provider_name": "ollama",
            "caller_context": caller_context,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "context": context,
        },
    )
    transcript_store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type="model_provider_completed",
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload={
            "request_id": request_id,
            "decision_id": decision_id,
            "caller_context": caller_context,
            "result": raw_response,
            "raw_response": raw_response,
            "token_usage": {
                "input_tokens": 12,
                "output_tokens": 7,
                "total_tokens": 19,
            },
            "model": "qwen2.5:7b",
            "elapsed_ms": 345,
        },
    )
    return {
        "trace_id": trace_id,
        "provider_name": "ollama",
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "system_prompt": system_prompt,
        "context": context,
        "raw_response": raw_response,
        "token_usage": {
            "input_tokens": 12,
            "output_tokens": 7,
            "total_tokens": 19,
        },
    }


def test_nine_question_trace_payload_is_reconstructed_from_real_transcript_store(acceptance_app: FastAPI) -> None:
    expected = _insert_model_trace_events(
        acceptance_app,
        question_id="q3",
        trace_id="q3:acceptance",
    )

    with TestClient(acceptance_app) as client:
        response = client.get("/api/web/nine-questions/q3/trace-payload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == expected["trace_id"]
    assert payload["provider_name"] == expected["provider_name"]
    assert payload["model"] == expected["model"]
    assert payload["prompt"] == expected["prompt"]
    assert payload["system_prompt"] == expected["system_prompt"]
    assert payload["context_data"] == expected["context"]
    assert payload["raw_response"] == expected["raw_response"]
    assert payload["token_usage"] == expected["token_usage"]


def test_q9_detail_exposes_llm_trace_payload_from_real_trace_detail(acceptance_app: FastAPI) -> None:
    expected = _insert_model_trace_events(
        acceptance_app,
        question_id="q9",
        trace_id="q9:acceptance",
    )

    with TestClient(acceptance_app) as client:
        response = client.get("/api/web/nine-questions/q9")

    assert response.status_code == 200
    payload = response.json()
    llm_trace_payload = payload["llm_trace_payload"]
    assert payload["trace_id"] == expected["trace_id"]
    assert llm_trace_payload["provider_name"] == expected["provider_name"]
    assert llm_trace_payload["model"] == expected["model"]
    assert llm_trace_payload["prompt"] == expected["prompt"]
    assert llm_trace_payload["context_data"] == expected["context"]
    assert llm_trace_payload["raw_response"] == expected["raw_response"]
