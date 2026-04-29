from __future__ import annotations

from importlib import import_module

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


EXPECTED_MODULE_IDS = {"cognition", "memory", "bridge", "safety", "network", "runtime"}
EXPECTED_REQUIRED_COMPONENTS = {
    "BrainRuntime",
    "BrainSession",
    "ThinkLoop",
    "CognitiveToolOrchestrator",
    "BrainTranscriptStore",
}


def _assert_g2_architecture_payload(payload: dict, *, expected_active_session_id: str) -> None:
    assert payload["feature_code"] == "G2"
    assert payload["status"] == "complete"
    assert payload["module_count"] == 6

    modules = payload["modules"]
    assert {item["module_id"] for item in modules} == EXPECTED_MODULE_IDS
    for item in modules:
        assert item["service_boundary_importable"] is True
        module_name, _, attr = item["service_boundary"].rpartition(".")
        module = import_module(module_name)
        assert hasattr(module, attr)
        assert item["responsibilities"], f"{item['module_id']} missing responsibilities"

    runtime = payload["runtime_container"]
    assert runtime["name"] == "BrainRuntime"
    assert runtime["implementation"] == "zentex.kernel.service.KernelService"
    assert runtime["holds_shared_dependencies"] is True
    assert "_environment_service" in runtime["injected_dependency_slots"]
    assert "_llm_service" in runtime["injected_dependency_slots"]

    session = payload["session_container"]
    assert session["name"] == "BrainSession"
    assert session["cross_turn_continuity"] is True
    assert expected_active_session_id in session["active_session_ids"]
    assert session["active_session_count"] >= 1

    think_loop = payload["think_loop"]
    assert think_loop["implementation"].endswith("ThinkLoop")
    assert think_loop["stateless"] is True
    assert "observe" in think_loop["phase_names"]
    assert "decision_synthesis" in think_loop["phase_names"]
    assert think_loop["nominal_nine_stage_contract"] is True

    components = payload["required_components"]
    assert {item["component"] for item in components} == EXPECTED_REQUIRED_COMPONENTS
    assert all(item["present"] is True for item in components)

    rules = payload["architecture_rules"]
    assert rules["external_modules_use_service_boundary"] is True
    assert rules["think_loop_persists_no_long_term_state"] is True
    assert rules["web_console_business_logic"] is False


def test_g2_core_architecture_snapshot_queries_real_kernel_components(real_ci_runtime) -> None:
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id="g2-architecture-service")

    payload = kernel_service.get_core_architecture_snapshot()

    _assert_g2_architecture_payload(payload, expected_active_session_id=session_id)
    queried = kernel_service.get_core_architecture_snapshot()
    assert queried["session_container"]["active_session_count"] == payload["session_container"]["active_session_count"]
    assert session_id in queried["session_container"]["active_session_ids"]


def test_g2_core_architecture_api_returns_real_query_result(real_ci_runtime) -> None:
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id="g2-architecture-api")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        response = requests.get(f"{base_url}/api/web/runtime/architecture", timeout=20)

    assert response.status_code == 200, response.text
    _assert_g2_architecture_payload(response.json(), expected_active_session_id=session_id)
