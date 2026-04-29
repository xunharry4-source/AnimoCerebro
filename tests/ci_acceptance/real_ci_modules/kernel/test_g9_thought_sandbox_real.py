from __future__ import annotations

from pathlib import Path

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _assert_destructive_veto(payload: dict, *, session_id: str) -> None:
    assert payload["feature_code"] == "G9"
    assert payload["scenario"]["session_id"] == session_id
    assert payload["scenario"]["action_type"] == "delete_file"
    assert payload["risk_score"] >= payload["scenario"]["catastrophe_threshold"]
    assert payload["vetoed"] is True
    assert payload["replan_required"] is True
    assert payload["side_effect_committed"] is False
    assert payload["recommended_action"] == "replan"
    assert "catastrophic_data_or_identity_loss_possible" in payload["catastrophe_predictions"]
    assert payload["veto_reason"] == "destructive_or_identity_action_requires_replan_before_execution"
    assert payload["plugin_contract"]["family"] == "simulation"
    assert payload["plugin_contract"]["required_method"] == "simulate_action"
    assert payload["evidence_refs"]


def test_g9_thought_sandbox_service_simulates_queries_and_preserves_no_side_effects_real(
    real_ci_runtime,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g9-service-{suffix}")
    probe_path = tmp_path / f"must-not-exist-{suffix}.txt"

    outcome = kernel_service.run_thought_sandbox_simulation(
        session_id=session_id,
        action_type="delete_file",
        action_payload={
            "target": str(probe_path),
            "parameters": {"recursive": True},
            "side_effect_probe_path": str(probe_path),
        },
        risk_level="critical",
        task_type="file_operation",
        domain="filesystem",
        branches=[{"branch_id": "delete", "label": "delete probe path"}],
        catastrophe_threshold=0.55,
    )

    _assert_destructive_veto(outcome, session_id=session_id)
    assert not probe_path.exists(), "ThoughtSandbox 预演不得创建或删除真实文件"
    queried = kernel_service.query_thought_sandbox_outcome(
        session_id=session_id,
        outcome_id=outcome["outcome_id"],
    )
    assert queried["query_visible"] is True
    assert queried["outcome_id"] == outcome["outcome_id"]
    assert queried["scenario"]["action_payload"]["target"] == str(probe_path)

    memory_ref = next(ref for ref in outcome["evidence_refs"] if ref["type"] == "memory")
    memory = real_ci_runtime.memory_service.get_record(memory_ref["memory_id"])
    assert memory is not None
    assert memory.target_id == outcome["scenario"]["scenario_id"]
    assert "thought_sandbox" in memory.tags

    safe = kernel_service.run_thought_sandbox_simulation(
        session_id=session_id,
        action_type="get_status",
        action_payload={"target": "runtime", "parameters": {"scope": suffix}},
        risk_level="low",
        task_type="status_query",
        domain="general",
        catastrophe_threshold=0.8,
    )
    assert safe["vetoed"] is False
    assert safe["replan_required"] is False
    assert safe["recommended_action"] == "allow_to_safety_gate"
    assert kernel_service.query_thought_sandbox_outcome(
        session_id=session_id,
        outcome_id=safe["outcome_id"],
    )["risk_score"] == safe["risk_score"]

    entries = kernel_service.get_transcript(session_id, limit=200)
    event_types = {entry["payload"].get("entry_type") for entry in entries if entry["payload"].get("feature_code") == "G9"}
    assert {"g9_thought_sandbox_simulated", "g9_thought_sandbox_queried"} <= event_types


def test_g9_thought_sandbox_api_requests_create_and_query_real(
    real_ci_runtime,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g9-api-{suffix}")
    probe_path = tmp_path / f"api-side-effect-{suffix}.txt"
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/runtime/thought-sandbox/simulations",
            json={
                "session_id": session_id,
                "action_type": "delete_file",
                "action_payload": {"target": str(probe_path), "parameters": {"recursive": True}},
                "risk_level": "critical",
                "task_type": "file_operation",
                "domain": "filesystem",
                "branches": [{"branch_id": "api-delete"}],
                "catastrophe_threshold": 0.55,
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        created = response.json()
        query_response = requests.get(
            f"{base_url}/api/web/runtime/thought-sandbox/outcomes/{created['outcome_id']}",
            params={"session_id": session_id},
            timeout=20,
        )

    _assert_destructive_veto(created, session_id=session_id)
    assert not Path(probe_path).exists()
    assert query_response.status_code == 200, query_response.text
    queried = query_response.json()
    assert queried["outcome_id"] == created["outcome_id"]
    assert queried["scenario"]["action_payload"]["target"] == str(probe_path)
