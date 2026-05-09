from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _assert_g3_status(payload: dict) -> None:
    assert payload["feature_code"] == "G3"
    assert payload["heartbeat_state"] in {"active", "paused", "degraded", "fused"}
    assert isinstance(payload["running"], bool)
    assert payload["tick_count"] >= 0
    assert payload["success_count"] >= 0
    assert payload["failure_count"] >= 0
    assert payload["consecutive_failures"] >= 0
    assert payload["max_consecutive_failures"] >= 1
    assert isinstance(payload["history"], list)


def _assert_g3_tick_transcript(kernel_service, *, session_id: str, trace_id: str) -> None:
    entries = kernel_service.get_transcript(session_id, limit=200)
    matches = [
        entry
        for entry in entries
        if entry["trace_id"] == trace_id
        and entry["payload"].get("feature_code") == "G3"
        and entry["payload"].get("entry_type") == "g3_brain_daemon_tick_completed"
    ]
    assert matches, f"G3 tick transcript not found for trace_id={trace_id}"
    payload = matches[0]["payload"]
    assert payload["heartbeat_state"] == "active"
    assert "physical_state" in payload["observation_keys"]
    assert "situation_impact" in payload["observation_keys"]


def test_g3_brain_daemon_service_controls_tick_pause_resume_and_persist_audit(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g3-service-{suffix}")

    started = kernel_service.control_brain_daemon(
        action="start",
        session_id=session_id,
        interval_seconds=0.2,
        max_consecutive_failures=2,
        run_background=False,
    )
    _assert_g3_status(started)
    assert started["running"] is True
    assert started["heartbeat_state"] == "active"

    ticked = kernel_service.control_brain_daemon(action="tick", session_id=session_id)
    _assert_g3_status(ticked)
    assert ticked["tick_executed"] is True
    assert ticked["tick_success"] is True
    assert ticked["tick_count"] == started["tick_count"] + 1
    assert ticked["success_count"] >= 1
    assert ticked["last_error"] == ""
    assert ticked["last_observation"]["session_id"] == session_id
    assert "physical_state" in ticked["last_observation"]["observation"]
    _assert_g3_tick_transcript(kernel_service, session_id=session_id, trace_id=ticked["last_trace_id"])

    paused = kernel_service.control_brain_daemon(action="pause", session_id=session_id)
    assert paused["heartbeat_state"] == "paused"
    skipped = kernel_service.control_brain_daemon(action="tick", session_id=session_id)
    assert skipped["tick_executed"] is False
    assert skipped["skip_reason"] == "paused"
    assert skipped["tick_count"] == ticked["tick_count"]

    resumed = kernel_service.control_brain_daemon(action="resume", session_id=session_id)
    assert resumed["heartbeat_state"] == "active"
    ticked_again = kernel_service.control_brain_daemon(action="tick", session_id=session_id)
    assert ticked_again["tick_success"] is True
    assert ticked_again["tick_count"] == ticked["tick_count"] + 1
    _assert_g3_tick_transcript(kernel_service, session_id=session_id, trace_id=ticked_again["last_trace_id"])

    stopped = kernel_service.control_brain_daemon(action="stop", session_id=session_id)
    assert stopped["running"] is False
    assert stopped["heartbeat_state"] == "paused"
    queried = kernel_service.get_brain_daemon_status()
    assert queried["running"] is False
    assert queried["tick_count"] == stopped["tick_count"]


def test_g3_brain_daemon_api_controls_are_real_requests_and_query_state(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g3-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        start_response = requests.post(
            f"{base_url}/api/web/runtime/daemon/control",
            json={
                "action": "start",
                "session_id": session_id,
                "interval_seconds": 0.2,
                "max_consecutive_failures": 2,
                "run_background": False,
            },
            timeout=20,
        )
        tick_response = requests.post(
            f"{base_url}/api/web/runtime/daemon/control",
            json={"action": "tick", "session_id": session_id},
            timeout=30,
        )
        status_response = requests.get(f"{base_url}/api/web/runtime/daemon/status", timeout=20)
        pause_response = requests.post(
            f"{base_url}/api/web/runtime/daemon/control",
            json={"action": "pause", "session_id": session_id},
            timeout=20,
        )
        skipped_response = requests.post(
            f"{base_url}/api/web/runtime/daemon/control",
            json={"action": "tick", "session_id": session_id},
            timeout=20,
        )
        stop_response = requests.post(
            f"{base_url}/api/web/runtime/daemon/control",
            json={"action": "stop", "session_id": session_id},
            timeout=20,
        )

    assert start_response.status_code == 200, start_response.text
    assert tick_response.status_code == 200, tick_response.text
    assert status_response.status_code == 200, status_response.text
    assert pause_response.status_code == 200, pause_response.text
    assert skipped_response.status_code == 200, skipped_response.text
    assert stop_response.status_code == 200, stop_response.text

    started = start_response.json()
    ticked = tick_response.json()
    queried = status_response.json()
    paused = pause_response.json()
    skipped = skipped_response.json()
    stopped = stop_response.json()

    _assert_g3_status(started)
    _assert_g3_status(ticked)
    _assert_g3_status(queried)
    assert ticked["tick_executed"] is True
    assert ticked["tick_success"] is True
    assert queried["last_trace_id"] == ticked["last_trace_id"]
    assert paused["heartbeat_state"] == "paused"
    assert skipped["tick_executed"] is False
    assert skipped["skip_reason"] == "paused"
    assert stopped["running"] is False
    _assert_g3_tick_transcript(kernel_service, session_id=session_id, trace_id=ticked["last_trace_id"])
