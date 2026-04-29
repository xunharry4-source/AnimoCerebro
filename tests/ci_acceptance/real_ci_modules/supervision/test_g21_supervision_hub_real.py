from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import socket
import threading
import time

import pytest
import requests
import uvicorn
from fastapi import FastAPI
from websockets.sync.client import connect as websocket_connect

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.supervision.hub import SupervisionHub, ThoughtTrace


@contextmanager
def _live_http_server(app: FastAPI) -> Iterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
    config = uvicorn.Config(app, host=host, port=port, log_level="critical", lifespan="off", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        raise RuntimeError("uvicorn live request server failed to start")
    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_g21_streamed_thought_traces_and_kill_switch_block_writes_until_manual_restore() -> None:
    suffix = unique_suffix()
    hub = SupervisionHub()
    session_id = f"g21-session-{suffix}"
    terminal_id = f"terminal-{suffix}"
    connected = hub.connect_terminal(terminal_id)
    assert connected.active_terminal_count == 1
    assert connected.continuously_supervised is True
    hub.append_thought_trace(ThoughtTrace(session_id=session_id, sequence=1, stage="q8", reasoning_summary="selected safe task", evidence_refs=["q8"]))
    hub.append_thought_trace(ThoughtTrace(session_id=session_id, sequence=2, stage="q9", reasoning_summary="prepared final posture", evidence_refs=["q9"]))
    with pytest.raises(ValueError):
        hub.append_thought_trace(ThoughtTrace(session_id=session_id, sequence=2, stage="duplicate", reasoning_summary="duplicate sequence"))

    traces = hub.list_thought_traces(session_id=session_id, after_sequence=1)
    assert len(traces) == 1
    assert traces[0].sequence == 2
    assert traces[0].stage == "q9"
    assert hub.get_state().continuously_supervised is True
    disconnected = hub.disconnect_terminal(terminal_id)
    assert disconnected.active_terminal_count == 0
    assert disconnected.continuously_supervised is False

    manual = hub.apply_intervention(
        action="manual_mode",
        reason="operator takes over planning",
        operator_id=f"operator-{suffix}",
    )
    assert manual.after_mode.value == "manual"
    with pytest.raises(RuntimeError):
        hub.assert_write_allowed({"action": "manual_write"})

    read_only = hub.apply_intervention(
        action="read_only",
        reason="operator restricts system to observation",
        operator_id=f"operator-{suffix}",
    )
    assert read_only.after_mode.value == "read_only"
    with pytest.raises(RuntimeError):
        hub.assert_write_allowed({"action": "write_during_read_only"})

    intervention = hub.apply_intervention(
        action="physical_kill_switch",
        reason="operator observed unsafe autonomous write",
        operator_id=f"operator-{suffix}",
    )
    assert intervention.before_mode.value == "read_only"
    assert intervention.after_mode.value == "fused"
    assert hub.get_state().write_allowed is False
    with pytest.raises(RuntimeError):
        hub.assert_write_allowed({"action": "ledger_set"})
    with pytest.raises(ValueError):
        hub.apply_intervention(action="restore_autonomy", reason="missing token", operator_id=f"operator-{suffix}")

    restored = hub.apply_intervention(
        action="restore_autonomy",
        reason="manual inspection completed",
        operator_id=f"operator-{suffix}",
        confirmation_token="manual-confirmed",
    )
    assert restored.after_mode.value == "autonomous"
    assert hub.get_state().write_allowed is True
    interventions = hub.list_interventions()
    assert [item.action for item in interventions] == ["manual_mode", "read_only", "physical_kill_switch", "restore_autonomy"]
    assert interventions[-1].confirmation_token == "manual-confirmed"


def test_g21_supervision_hub_api_uses_requests_and_returns_exact_state(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.supervision_hub = SupervisionHub()
    session_id = f"g21-api-session-{suffix}"
    terminal_id = f"api-terminal-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        initial_write_response = requests.post(
            f"{base_url}/api/web/supervision-hub/write-check",
            json={"action_payload": {"operation": "initial-write-probe", "suffix": suffix}},
            timeout=10,
        )
        assert initial_write_response.status_code == 200, initial_write_response.text
        assert initial_write_response.json()["write_allowed"] is True

        connect_response = requests.post(
            f"{base_url}/api/web/supervision-hub/terminals/{terminal_id}/connect",
            timeout=10,
        )
        assert connect_response.status_code == 200, connect_response.text
        assert connect_response.json()["active_terminal_count"] == 1
        assert connect_response.json()["continuously_supervised"] is True

        trace_response = requests.post(
            f"{base_url}/api/web/supervision-hub/thought-traces",
            json={
                "session_id": session_id,
                "sequence": 7,
                "stage": "critical_decision",
                "reasoning_summary": "manual observer sees critical decision chain",
                "evidence_refs": ["trace://critical-decision"],
            },
            timeout=10,
        )
        assert trace_response.status_code == 200, trace_response.text
        duplicate_response = requests.post(
            f"{base_url}/api/web/supervision-hub/thought-traces",
            json={
                "session_id": session_id,
                "sequence": 7,
                "stage": "duplicate",
                "reasoning_summary": "duplicate sequence must be rejected",
            },
            timeout=10,
        )
        assert duplicate_response.status_code == 409, duplicate_response.text
        list_response = requests.get(
            f"{base_url}/api/web/supervision-hub/thought-traces",
            params={"session_id": session_id, "after_sequence": 6},
            timeout=10,
        )
        intervention_response = requests.post(
            f"{base_url}/api/web/supervision-hub/interventions",
            json={
                "action": "pause_autonomy",
                "reason": "operator pauses autonomous mode through API",
                "operator_id": f"api-operator-{suffix}",
            },
            timeout=10,
        )
        paused_write_response = requests.post(
            f"{base_url}/api/web/supervision-hub/write-check",
            json={"action_payload": {"operation": "write-while-paused", "suffix": suffix}},
            timeout=10,
        )
        manual_response = requests.post(
            f"{base_url}/api/web/supervision-hub/interventions",
            json={
                "action": "manual_mode",
                "reason": "operator takes manual control through API",
                "operator_id": f"api-operator-{suffix}",
            },
            timeout=10,
        )
        read_only_response = requests.post(
            f"{base_url}/api/web/supervision-hub/interventions",
            json={
                "action": "read_only",
                "reason": "operator switches API session to read only",
                "operator_id": f"api-operator-{suffix}",
            },
            timeout=10,
        )
        kill_response = requests.post(
            f"{base_url}/api/web/supervision-hub/interventions",
            json={
                "action": "physical_kill_switch",
                "reason": "operator validates physical fuse through API",
                "operator_id": f"api-operator-{suffix}",
            },
            timeout=10,
        )
        restore_without_token_response = requests.post(
            f"{base_url}/api/web/supervision-hub/interventions",
            json={
                "action": "restore_autonomy",
                "reason": "missing manual token must fail",
                "operator_id": f"api-operator-{suffix}",
            },
            timeout=10,
        )
        restore_response = requests.post(
            f"{base_url}/api/web/supervision-hub/interventions",
            json={
                "action": "restore_autonomy",
                "reason": "manual inspection completed through API",
                "operator_id": f"api-operator-{suffix}",
                "confirmation_token": "manual-confirmed",
            },
            timeout=10,
        )
        interventions_response = requests.get(f"{base_url}/api/web/supervision-hub/interventions", timeout=10)
        disconnect_response = requests.post(
            f"{base_url}/api/web/supervision-hub/terminals/{terminal_id}/disconnect",
            timeout=10,
        )
        state_response = requests.get(f"{base_url}/api/web/supervision-hub/state", timeout=10)
        restored_write_response = requests.post(
            f"{base_url}/api/web/supervision-hub/write-check",
            json={"action_payload": {"operation": "write-after-restore", "suffix": suffix}},
            timeout=10,
        )

    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["session_id"] == session_id
    assert listed[0]["sequence"] == 7
    assert intervention_response.status_code == 200
    assert intervention_response.json()["after_mode"] == "paused"
    assert paused_write_response.status_code == 423
    assert paused_write_response.json()["detail"]["mode"] == "paused"
    assert paused_write_response.json()["detail"]["write_allowed"] is False
    assert manual_response.status_code == 200, manual_response.text
    assert manual_response.json()["after_mode"] == "manual"
    assert read_only_response.status_code == 200, read_only_response.text
    assert read_only_response.json()["after_mode"] == "read_only"
    assert kill_response.status_code == 200, kill_response.text
    assert kill_response.json()["after_mode"] == "fused"
    assert restore_without_token_response.status_code == 409
    assert "manual-confirmed" in restore_without_token_response.json()["detail"]
    assert restore_response.status_code == 200, restore_response.text
    assert restore_response.json()["after_mode"] == "autonomous"
    assert interventions_response.status_code == 200
    interventions = interventions_response.json()
    assert [item["action"] for item in interventions] == [
        "pause_autonomy",
        "manual_mode",
        "read_only",
        "physical_kill_switch",
        "restore_autonomy",
    ]
    assert disconnect_response.status_code == 200
    assert disconnect_response.json()["active_terminal_count"] == 0
    assert disconnect_response.json()["continuously_supervised"] is False
    assert state_response.status_code == 200
    assert state_response.json()["mode"] == "autonomous"
    assert state_response.json()["write_allowed"] is True
    assert state_response.json()["continuously_supervised"] is False
    assert restored_write_response.status_code == 200
    assert restored_write_response.json()["write_allowed"] is True


def test_g21_supervision_hub_websocket_streams_real_trace_and_disconnects_terminal(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.supervision_hub = SupervisionHub()
    session_id = f"g21-stream-session-{suffix}"
    terminal_id = f"stream-terminal-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        ws_url = base_url.replace("http://", "ws://") + (
            f"/api/web/supervision-hub/thought-stream?session_id={session_id}"
            f"&after_sequence=0&terminal_id={terminal_id}"
        )
        with websocket_connect(ws_url, open_timeout=10) as websocket:
            connected_state = requests.get(f"{base_url}/api/web/supervision-hub/state", timeout=10)
            assert connected_state.status_code == 200
            assert connected_state.json()["active_terminal_count"] == 1
            assert connected_state.json()["continuously_supervised"] is True

            trace_response = requests.post(
                f"{base_url}/api/web/supervision-hub/thought-traces",
                json={
                    "session_id": session_id,
                    "sequence": 1,
                    "stage": "streamed_supervision",
                    "reasoning_summary": "streaming observer receives the real trace",
                    "evidence_refs": [f"trace://g21/{suffix}"],
                },
                timeout=10,
            )
            assert trace_response.status_code == 200, trace_response.text
            received = json.loads(websocket.recv(timeout=10))
            assert received["session_id"] == session_id
            assert received["sequence"] == 1
            assert received["stage"] == "streamed_supervision"
            assert received["evidence_refs"] == [f"trace://g21/{suffix}"]

        disconnected_state = requests.get(f"{base_url}/api/web/supervision-hub/state", timeout=10)

    assert disconnected_state.status_code == 200
    assert disconnected_state.json()["active_terminal_count"] == 0
    assert disconnected_state.json()["continuously_supervised"] is False
