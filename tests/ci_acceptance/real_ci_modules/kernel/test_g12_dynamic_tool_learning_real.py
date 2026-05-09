from __future__ import annotations

from typing import Any

import pytest
import requests
from fastapi import FastAPI, Request

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _tool_doc_app(*, suffix: str, wrong_output: bool = False) -> FastAPI:
    app = FastAPI()

    @app.get("/docs/weather-tool.json")
    def tool_doc(request: Request) -> dict[str, Any]:
        base = str(request.base_url).rstrip("/")
        return {
            "tool_name": f"g12_weather_lookup_{suffix}",
            "version": "1.0.0",
            "description": "Lookup deterministic weather facts for verification.",
            "usage_example": {"city": "Shanghai"},
            "input_schema": {"type": "object", "required": ["city"], "properties": {"city": {"type": "string"}}},
            "output_schema": {"type": "object", "required": ["temperature_c", "condition"]},
            "verification_endpoint": f"{base}/tools/weather/verify",
            "verification_cases": [
                {
                    "input": {"city": "Shanghai"},
                    "expected_output": {"temperature_c": 21, "condition": "clear"},
                }
            ],
        }

    @app.get("/docs/static-catalog-sample.json")
    def static_doc(request: Request) -> dict[str, Any]:
        base = str(request.base_url).rstrip("/")
        return {
            "tool_name": f"g12_static_catalog_{suffix}",
            "version": "0.1.0",
            "description": "Static catalog sample must not become real verified.",
            "usage_example": {"city": "Shanghai"},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "verification_endpoint": f"{base}/tools/weather/verify",
            "verification_cases": [
                {
                    "input": {"city": "Shanghai"},
                    "expected_output": {"temperature_c": 21, "condition": "clear"},
                }
            ],
        }

    @app.post("/tools/weather/verify")
    def verify(payload: dict[str, Any]) -> dict[str, Any]:
        assert payload == {"city": "Shanghai"}
        if wrong_output:
            return {"temperature_c": -99, "condition": "wrong"}
        return {"temperature_c": 21, "condition": "clear", "source": "real_http_verifier"}

    return app


def _assert_real_verified(result: dict[str, Any], *, session_id: str, suffix: str) -> None:
    assert result["feature_code"] == "G12"
    assert result["session_id"] == session_id
    assert result["registered"] is True
    assert result["capability_id"]
    assert result["tool_knowledge_record"]["tool_name"] == f"g12_weather_lookup_{suffix}"
    assert result["tool_knowledge_record"]["verification_status"] == "real_verified"
    assert result["verification"]["verification_status"] == "real_verified"
    assert result["verification"]["registered"] is True
    assert result["verification"]["failure_samples"] == []
    assert len(result["verification"]["receipts"]) == 1
    receipt = result["verification"]["receipts"][0]
    assert receipt["passed"] is True
    assert receipt["input"] == {"city": "Shanghai"}
    assert receipt["expected_output"] == {"temperature_c": 21, "condition": "clear"}
    assert receipt["actual_output"]["temperature_c"] == 21
    assert receipt["actual_output"]["condition"] == "clear"
    assert result["capability_registration"]["status"] == "active"
    assert result["capability_registration"]["verification_status"] == "real_verified"
    assert result["sandbox_outcome_ref"]
    assert {ref["type"] for ref in result["evidence_refs"]} >= {"memory", "thought_sandbox"}


def test_g12_dynamic_tool_learning_service_reads_real_doc_verifies_registers_and_queries_real_http(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g12-service-{suffix}")

    with live_http_server(_tool_doc_app(suffix=suffix)) as doc_url:
        learned = kernel_service.learn_dynamic_tool_capability(
            session_id=session_id,
            documentation_url=f"{doc_url}/docs/weather-tool.json",
            source_kind="real_document",
            timeout_seconds=2,
        )

    _assert_real_verified(learned, session_id=session_id, suffix=suffix)
    knowledge = kernel_service.query_tool_knowledge_record(
        session_id=session_id,
        knowledge_id=learned["knowledge_id"],
    )
    assert knowledge["query_visible"] is True
    assert knowledge["knowledge_id"] == learned["knowledge_id"]
    assert knowledge["tool_knowledge_record"] == learned["tool_knowledge_record"]
    capability = kernel_service.query_capability_registration(
        session_id=session_id,
        capability_id=learned["capability_id"],
    )
    assert capability["query_visible"] is True
    assert capability["capability_id"] == learned["capability_id"]
    assert capability["tool_name"] == f"g12_weather_lookup_{suffix}"

    memory_ref = next(ref for ref in learned["evidence_refs"] if ref["type"] == "memory")
    memory = real_ci_runtime.memory_service.get_record(memory_ref["memory_id"])
    assert memory is not None
    assert memory.target_id == learned["capability_id"]
    assert "G12" in memory.tags
    assert "real_verified" in memory.tags

    entries = kernel_service.get_transcript(session_id, limit=300)
    event_types = {entry["payload"].get("entry_type") for entry in entries if entry["payload"].get("feature_code") == "G12"}
    assert {
        "g12_dynamic_tool_learning_completed",
        "g12_tool_knowledge_queried",
        "g12_capability_registration_queried",
    } <= event_types


def test_g12_dynamic_tool_learning_does_not_register_static_sample_or_failed_verification_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g12-negative-{suffix}")

    with live_http_server(_tool_doc_app(suffix=suffix)) as doc_url:
        static_result = kernel_service.learn_dynamic_tool_capability(
            session_id=session_id,
            documentation_url=f"{doc_url}/docs/static-catalog-sample.json",
            source_kind="static_catalog_sample",
            timeout_seconds=2,
        )
    assert static_result["registered"] is False
    assert static_result["capability_id"] is None
    assert static_result["tool_knowledge_record"]["verification_status"] == "simulated_learned"
    assert static_result["verification"]["reason"] == "static_catalog_sample_cannot_be_real_verified"
    queried_static = kernel_service.query_tool_knowledge_record(
        session_id=session_id,
        knowledge_id=static_result["knowledge_id"],
    )
    assert queried_static["registered"] is False

    with live_http_server(_tool_doc_app(suffix=suffix, wrong_output=True)) as doc_url:
        failed = kernel_service.learn_dynamic_tool_capability(
            session_id=session_id,
            documentation_url=f"{doc_url}/docs/weather-tool.json",
            source_kind="real_document",
            timeout_seconds=2,
        )
    assert failed["registered"] is False
    assert failed["capability_id"] is None
    assert failed["verification"]["verification_status"] == "verification_failed"
    assert failed["verification"]["failure_samples"][0]["reason"] == "output_mismatch"
    assert failed["verification"]["receipts"][0]["passed"] is False
    with pytest.raises(KeyError):
        kernel_service.query_capability_registration(session_id=session_id, capability_id="missing-g12-capability")


def test_g12_dynamic_tool_learning_api_requests_learn_query_and_capability_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g12-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    runtime_app = FastAPI()
    runtime_app.include_router(api_router)

    with live_http_server(_tool_doc_app(suffix=suffix)) as doc_url, live_http_server(runtime_app) as base_url:
        learn_response = requests.post(
            f"{base_url}/api/web/runtime/dynamic-tools/learn",
            json={
                "session_id": session_id,
                "documentation_url": f"{doc_url}/docs/weather-tool.json",
                "source_kind": "real_document",
                "timeout_seconds": 2,
            },
            timeout=20,
        )
        assert learn_response.status_code == 200, learn_response.text
        learned = learn_response.json()
        knowledge_response = requests.get(
            f"{base_url}/api/web/runtime/dynamic-tools/knowledge/{learned['knowledge_id']}",
            params={"session_id": session_id},
            timeout=20,
        )
        capability_response = requests.get(
            f"{base_url}/api/web/runtime/dynamic-tools/capabilities/{learned['capability_id']}",
            params={"session_id": session_id},
            timeout=20,
        )

    _assert_real_verified(learned, session_id=session_id, suffix=suffix)
    assert knowledge_response.status_code == 200, knowledge_response.text
    knowledge = knowledge_response.json()
    assert knowledge["query_visible"] is True
    assert knowledge["knowledge_id"] == learned["knowledge_id"]
    assert knowledge["tool_knowledge_record"]["source_ref"] == learned["documentation"]["url"]
    assert capability_response.status_code == 200, capability_response.text
    capability = capability_response.json()
    assert capability["query_visible"] is True
    assert capability["capability_id"] == learned["capability_id"]
    assert capability["verification_receipts"] == learned["verification"]["receipts"]
