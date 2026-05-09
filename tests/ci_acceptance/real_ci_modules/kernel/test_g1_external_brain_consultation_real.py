from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import socket
import threading
import time

import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _g1_context(suffix: str) -> dict:
    return {
        "workspace_state": {
            "workspace_id": f"g1-workspace-{suffix}",
            "current_goal": "判断宿主是否应该执行一次受控资料整理任务",
            "dirty_files": [],
        },
        "host_context": {
            "host_agent_id": f"host-agent-{suffix}",
            "host_agent_type": "external_agent",
            "host_can_run_without_zentex": True,
        },
        "external_signals": [
            {
                "source": "ci_real_g1",
                "signal_type": "task_request",
                "content": "整理指定资料，但最终执行权留给宿主 Agent。",
            }
        ],
        "long_term_memory": [
            {
                "memory_id": f"g1-memory-{suffix}",
                "content": "Zentex 只提供认知建议，不直接接管宿主执行。",
            }
        ],
    }


def _assert_g1_business_response(payload: dict, *, session_id: str, trace_id: str | None = None) -> None:
    assert payload["feature_code"] == "G1"
    assert payload["session_id"] == session_id
    if trace_id is not None:
        assert payload["trace_id"] == trace_id
    assert payload["role"] == "external_brain"
    assert payload["live_llm_used"] is True
    assert payload["host_retains_final_execution"] is True
    assert payload["zentex_will_not_execute"] is True

    task_judgment = payload["task_judgment"]
    assert isinstance(task_judgment["summary"], str)
    assert task_judgment["summary"].strip()
    assert str(task_judgment["should_execute"]).strip()
    assert str(task_judgment["risk_level"]).strip()
    assert "confidence" in task_judgment

    advice = payload["decision_advice"]
    assert advice["host_execution_owner"] == "host_agent"
    assert advice["zentex_role"] == "external_brain_advisor"
    assert advice["host_retains_final_execution"] is True
    assert advice["zentex_will_not_execute"] is True
    assert isinstance(advice["recommendation"], str)
    assert advice["recommendation"].strip()
    assert isinstance(advice["next_steps"], list)
    assert isinstance(advice["boundaries"], list)

    nine = payload["nine_question_analysis"]
    assert sorted(nine.keys()) == [f"q{i}" for i in range(1, 10)]
    for question_id, question_payload in nine.items():
        assert question_id.startswith("q")
        assert isinstance(question_payload, dict)
        assert str(question_payload.get("answer") or question_payload.get("summary") or "").strip()

    audit = payload["audit"]
    assert audit["transcript_written"] is True
    assert str(audit["llm_provider_key"]).strip()
    assert str(audit["llm_model"]).strip()
    assert set(audit["llm_usage"]) == {"input_tokens", "output_tokens", "total_tokens"}


def _assert_g1_transcript(kernel_service, *, session_id: str, trace_id: str) -> None:
    entries = kernel_service.get_transcript(session_id, limit=100)
    g1_entries = [
        entry
        for entry in entries
        if entry["trace_id"] == trace_id and entry["payload"].get("feature_code") == "G1"
    ]
    event_names = {entry["payload"]["entry_type"] for entry in g1_entries}
    assert "g1_bridge_request_received" in event_names
    assert "g1_live_llm_semantic_fill_completed" in event_names
    assert "g1_advice_returned_to_host" in event_names

    returned = next(entry for entry in g1_entries if entry["payload"]["entry_type"] == "g1_advice_returned_to_host")
    assert returned["payload"]["host_retains_final_execution"] is True
    assert returned["payload"]["zentex_will_not_execute"] is True
    assert returned["payload"]["decision_advice"]["host_execution_owner"] == "host_agent"


@contextmanager
def _live_http_server(app: FastAPI) -> Iterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="critical",
        lifespan="off",
        access_log=False,
    )
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


def test_kernel_service_consult_external_brain_writes_real_g1_transcript(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g1-service-{suffix}")
    trace_id = f"g1-service-trace-{suffix}"

    payload = kernel_service.consult_external_brain(
        session_id=session_id,
        user_input="请判断宿主 Agent 是否应该继续执行资料整理任务，并给出只作为建议的下一步。",
        context=_g1_context(suffix),
        trace_id=trace_id,
    )

    _assert_g1_business_response(payload, session_id=session_id, trace_id=trace_id)
    _assert_g1_transcript(kernel_service, session_id=session_id, trace_id=trace_id)


def test_external_brain_consult_api_uses_real_requests_and_persists_g1_audit(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g1-api-{suffix}")
    trace_id = f"g1-api-trace-{suffix}"

    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with _live_http_server(app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/external-brain/consult",
            json={
                "session_id": session_id,
                "user_input": "通过 API 请求 Zentex 判断任务方向，但不得替宿主执行。",
                "context": _g1_context(suffix),
                "trace_id": trace_id,
            },
            timeout=240,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    _assert_g1_business_response(payload, session_id=session_id, trace_id=trace_id)
    _assert_g1_transcript(kernel_service, session_id=session_id, trace_id=trace_id)
