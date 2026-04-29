from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import socket
import threading
import time

import pytest
import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


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


def _q9_snapshot(suffix: str) -> dict:
    evaluation_profile = {
        "role_context": "api replay verifier",
        "resource_context": "real acceptance app task service",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.3,
            "risk_control": 0.5,
            "continuity": 0.15,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "api_trace_integrity",
        "action_rhythm_hint": "query_after_every_write",
    }
    return {
        "trace_id": f"trace-q9-replay-api-{suffix}",
        "summary": "Q9 replay integrity API profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int) -> dict:
    rows = [
        {
            "task_id": f"q8-replay-api-task-{suffix}-{index:03d}",
            "title": f"q8 replay API integrity task {suffix} #{index:03d}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["api replay integrity report matches outcome"],
            "expected_outcome": {"replay_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-replay-api-{suffix}",
            "summary": "Q8 replay integrity API test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"replay API integrity mission {suffix}",
                    "primary_objectives": ["verify replay integrity API"],
                    "secondary_objectives": ["preserve q8/q9 trace chain"],
                    "completion_conditions": ["all replay API outcomes passed"],
                    "pause_conditions": ["missing replay API outcome"],
                    "escalation_conditions": ["replay API trace chain broken"],
                },
                "q8_task_queue": {
                    "next_self_tasks": rows,
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        },
        "q9": _q9_snapshot(suffix),
    }


@pytest.mark.asyncio
async def test_q8_replay_integrity_api_returns_exact_real_task_outcome_report(acceptance_app: FastAPI) -> None:
    """查询 API：真实同步/完成任务后，HTTP 返回必须逐字段符合业务结果。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-api-{suffix}"
    expected_count = 100

    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, expected_count),
    )

    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == expected_count
    for task in tasks:
        completed = await acceptance_app.state.task_service.complete_task_with_verification(
            task.task_id,
            result={
                "actual_outcome": {
                    "task_id": task.task_id,
                    "title": task.title,
                    "q8_trace_id": task.metadata["trace_id"],
                },
                "evidence": [f"real api replay receipt for {task.task_id}"],
            },
            remarks="real api replay integrity receipt",
        )
        assert completed["success"] is True
        assert acceptance_app.state.task_service.get_task_outcome(task.task_id)["overall_passed"] is True

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/replay-integrity",
            params={"session_id": session_id, "expected_task_count": expected_count},
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["integrity_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["expected_task_count"] == expected_count
    assert payload["checked_task_count"] == expected_count
    assert payload["checked_outcome_count"] == expected_count
    assert payload["unique_q8_trace_count"] == 1
    assert len(payload["receipts"]) == expected_count
    assert {
        receipt["q8_trace_id"] for receipt in payload["receipts"]
    } == {f"trace-q8-replay-api-{suffix}"}
    assert {
        receipt["q9_trace_id"] for receipt in payload["receipts"]
    } == {f"trace-q9-replay-api-{suffix}"}
    assert all(receipt["priority"] == "high" for receipt in payload["receipts"])
    assert all(receipt["outcome_passed"] is True for receipt in payload["receipts"])
    assert {
        receipt["actual_outcome"]["task_id"] for receipt in payload["receipts"]
    } == {task.task_id for task in tasks}
    assert payload["require_writebacks"] is False
    assert payload["writeback_counts"] == {"reflection": 0, "memory": 0, "learning": 0}
    assert all(
        receipt["writebacks"] == {
            "reflection": {"written": False, "id": None, "verified": False},
            "memory": {"written": False, "id": None, "verified": False},
            "learning": {"written": False, "trace_id": None, "verified": False},
        }
        for receipt in payload["receipts"]
    )


@pytest.mark.asyncio
async def test_q8_replay_integrity_api_requires_real_writebacks_when_requested(acceptance_app: FastAPI) -> None:
    """查询 API：require_writebacks=true 时必须真实写入三类存储并在 HTTP 返回中逐项可查。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-api-writebacks-{suffix}"

    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    completed = await acceptance_app.state.task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {
                "task_id": task.task_id,
                "title": task.title,
                "q8_trace_id": task.metadata["trace_id"],
                "writeback_required": True,
            },
            "evidence": [f"real api writeback receipt for {task.task_id}"],
        },
        remarks="real api replay writeback receipt",
    )
    assert completed["success"] is True
    before = acceptance_app.state.task_service.get_task_outcome(task.task_id)
    assert before["written_back_to_reflection"] is False
    assert before["written_back_to_memory"] is False
    assert before["written_back_to_learning"] is False

    reflection = acceptance_app.state.task_service.write_task_outcome_to_reflection(
        acceptance_app.state.reflection_service,
        task.task_id,
    )
    memory = acceptance_app.state.task_service.write_task_outcome_to_memory(
        acceptance_app.state.memory_service,
        task.task_id,
    )
    learning = acceptance_app.state.task_service.write_task_outcome_to_learning(
        acceptance_app.state.learning_service,
        task.task_id,
    )
    after = acceptance_app.state.task_service.get_task_outcome(task.task_id)
    assert after["reflection_id"] == reflection["reflection_id"]
    assert after["memory_id"] == memory["memory_id"]
    assert after["learning_trace_id"] == learning["learning_trace_id"]

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/replay-integrity",
            params={
                "session_id": session_id,
                "expected_task_count": 1,
                "require_writebacks": "true",
            },
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["integrity_status"] == "passed"
    assert payload["require_writebacks"] is True
    assert payload["writeback_counts"] == {"reflection": 1, "memory": 1, "learning": 1}
    assert payload["receipts"][0]["task_id"] == task.task_id
    assert payload["receipts"][0]["writebacks"] == {
        "reflection": {"written": True, "id": reflection["reflection_id"], "verified": True},
        "memory": {"written": True, "id": memory["memory_id"], "verified": True},
        "learning": {"written": True, "trace_id": learning["learning_trace_id"], "verified": True},
    }


@pytest.mark.asyncio
async def test_q8_replay_integrity_api_returns_409_with_real_missing_outcome_failure(acceptance_app: FastAPI) -> None:
    """异常 API：缺 outcome 时必须 409 并返回真实失败原因，不返回空成功报告。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-api-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/replay-integrity",
            params={"session_id": session_id, "expected_task_count": 1},
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_replay_integrity_failed"
    assert detail["session_id"] == session_id
    assert detail["failures"] == [{"reason": "task_outcome_missing", "task_id": task.task_id}]


@pytest.mark.asyncio
async def test_q8_replay_integrity_api_returns_409_when_required_writebacks_are_missing(
    acceptance_app: FastAPI,
) -> None:
    """异常 API：要求写回但未写回时，HTTP 409 必须逐项返回缺失写回原因。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-api-missing-writebacks-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    completed = await acceptance_app.state.task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {"task_id": task.task_id, "q8_trace_id": task.metadata["trace_id"]},
            "evidence": [f"real api missing writeback receipt for {task.task_id}"],
        },
        remarks="real api missing writeback source outcome",
    )
    assert completed["success"] is True
    outcome = acceptance_app.state.task_service.get_task_outcome(task.task_id)
    assert outcome["written_back_to_reflection"] is False
    assert outcome["written_back_to_memory"] is False
    assert outcome["written_back_to_learning"] is False

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/replay-integrity",
            params={
                "session_id": session_id,
                "expected_task_count": 1,
                "require_writebacks": "true",
            },
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_replay_integrity_failed"
    assert detail["session_id"] == session_id
    assert detail["failures"] == [
        {"reason": "reflection_writeback_missing", "task_id": task.task_id},
        {"reason": "memory_writeback_missing", "task_id": task.task_id},
        {"reason": "learning_writeback_missing", "task_id": task.task_id},
    ]
