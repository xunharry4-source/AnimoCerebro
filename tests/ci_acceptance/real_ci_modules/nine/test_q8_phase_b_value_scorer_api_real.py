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
        "role_context": "phase b api rule scorer",
        "resource_context": "real API task outcome scoring",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.55,
            "continuity": 0.15,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "phase_b_api_rule_scoring",
        "action_rhythm_hint": "api_score_after_real_outcome",
    }
    return {
        "trace_id": f"trace-q9-phase-b-api-score-{suffix}",
        "summary": "Q9 Phase B API score profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int = 2) -> dict:
    rows = [
        {
            "task_id": f"phase-b-api-score-{suffix}-{index}",
            "title": f"phase b API value score task {suffix} #{index}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["value score API verifies outcome quality"],
            "expected_outcome": {"score_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-api-score-{suffix}",
            "summary": "Q8 Phase B API scoring test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b API scoring mission {suffix}",
                    "primary_objectives": ["score real q8 task outcomes through API"],
                    "secondary_objectives": ["preserve API scoring evidence"],
                    "completion_conditions": ["all API value score dimensions pass"],
                    "pause_conditions": ["missing API task outcome"],
                    "escalation_conditions": ["low API value score"],
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


async def _complete_with_good_outcome(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {
                "task_id": task.task_id,
                "title": task.title,
                "q8_trace_id": task.metadata["trace_id"],
                "evidence": [f"real phase b API scoring evidence for {task.task_id}"],
            },
            "evidence": [f"real phase b API scoring receipt for {task.task_id}"],
        },
        remarks="phase b API value scoring receipt",
    )
    assert completed["success"] is True
    persisted = task_service.get_task_outcome(task.task_id)
    assert persisted is not None
    assert persisted["overall_passed"] is True
    assert persisted["actual_outcome"]["evidence"]


@pytest.mark.asyncio
async def test_q8_phase_b_value_score_api_returns_exact_real_rule_scores(acceptance_app: FastAPI) -> None:
    """查询 API：真实任务和真实 outcome 通过规则评分后，HTTP 返回必须逐字段匹配业务结果。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-api-score-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 2),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    for task in tasks:
        await _complete_with_good_outcome(acceptance_app.state.task_service, task)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/value-score",
            params={"session_id": session_id, "expected_task_count": 2, "minimum_overall_score": 0.75},
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["value_score_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["scorer_layer"] == "phase_b_rule_based"
    assert payload["scored_task_count"] == 2
    assert payload["average_overall_score"] == 1.0
    assert payload["average_dimension_scores"] == {
        "evidence_completeness": 1.0,
        "lens_activation": 1.0,
        "outcome_verification": 1.0,
        "risk_control_alignment": 1.0,
    }
    assert payload["dominant_lens_counts"] == {"accuracy": 0, "risk_control": 2, "continuity": 0}
    assert {receipt["task_id"] for receipt in payload["receipts"]} == {task.task_id for task in tasks}
    assert all(receipt["overall_score"] == 1.0 for receipt in payload["receipts"])


@pytest.mark.asyncio
async def test_q8_phase_b_value_score_api_returns_409_when_real_outcome_is_missing(
    acceptance_app: FastAPI,
) -> None:
    """异常 API：缺真实 task_outcome 时，HTTP 必须 409 并返回真实 task_id。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-api-score-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    assert acceptance_app.state.task_service.get_task_outcome(task.task_id) is None

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/value-score",
            params={"session_id": session_id, "expected_task_count": 1},
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_b_value_scoring_failed"
    assert detail["session_id"] == session_id
    assert detail["failures"] == [{"reason": "task_outcome_missing", "task_id": task.task_id}]


@pytest.mark.asyncio
async def test_q8_phase_b_value_score_api_returns_409_for_real_failed_verification(
    acceptance_app: FastAPI,
) -> None:
    """异常 API：真实 verification 失败 outcome 必须返回维度失败和低分失败。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-api-score-low-{suffix}"
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
            }
        },
        remarks="phase b API low score source outcome",
    )
    assert completed["success"] is False
    assert acceptance_app.state.task_service.get_task_outcome(task.task_id)["overall_passed"] is False

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/value-score",
            params={"session_id": session_id, "expected_task_count": 1, "minimum_overall_score": 0.75},
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_b_value_scoring_failed"
    reasons = [failure["reason"] for failure in detail["failures"]]
    assert reasons == ["phase_b_task_dimension_failed", "phase_b_task_score_below_threshold"]
    assert detail["failures"][0]["failed_dimensions"] == ["outcome_verification", "evidence_completeness"]
    assert detail["failures"][1]["overall_score"] == 0.35
