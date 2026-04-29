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


def _snapshot(session_id: str, suffix: str, count: int) -> dict:
    rows = [
        {
            "task_id": f"phase-api-v1-{suffix}-{index}",
            "title": f"phase api v1 task {suffix} #{index}",
            "priority": "high",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["api report must query real task outcome"],
            "expected_outcome": {"index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "medium"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-api-v1-{suffix}",
            "summary": "Q8 V1 API evidence gate test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"v1 api evidence gates {suffix}",
                    "primary_objectives": ["serve production and living self model reports"],
                    "secondary_objectives": ["preserve real query evidence"],
                    "completion_conditions": ["api returns business fields"],
                    "pause_conditions": ["task outcome missing"],
                    "escalation_conditions": ["gate fails closed"],
                },
                "q8_task_queue": {
                    "next_self_tasks": rows,
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


async def _complete_good(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {"task_id": task.task_id, "kind": "api-success"},
            "evidence": [f"api evidence for {task.task_id}"],
        },
        remarks="v1 api evidence outcome",
    )
    assert completed["success"] is True
    assert task_service.get_task_outcome(task.task_id)["overall_passed"] is True


async def _write_production_metadata(task_service, task, suffix: str, index: int) -> None:
    review = {
        "review_id": f"api-prod-review-{suffix}-{index}",
        "reviewer_id": f"api-prod-reviewer-{suffix}",
        "reviewed_at": f"2026-04-{21 + index:02d}T09:00:00+08:00",
        "task_id": task.task_id,
        "q8_trace_id": task.metadata["trace_id"],
        "scorer_layer": "phase_b_rule_based",
        "scorer_decision": "accept",
        "human_label": "accept",
        "review_evidence": [f"api production review evidence {task.task_id}"],
    }
    production_observation = {
        "source": "production_history",
        "environment": "production",
        "sample_id": f"api-prod-q8-{suffix}-{index}",
        "observed_at": f"2026-04-{21 + index:02d}T10:00:00+08:00",
        "evidence": [f"api production export row {task.task_id}"],
    }
    realtime_gate = {
        "enabled": True,
        "decision": "accept",
        "overall_score": 1.0,
        "dimensions": {"production_history": 1.0},
        "dimension_failures": {},
        "threshold": {"accept_threshold": 0.75, "reject_threshold": 0.4},
    }
    await task_service.update_task_metadata(
        task.task_id,
        {
            "phase_b_manual_review": review,
            "phase_b_production_observation": production_observation,
            "phase_b_realtime_gate": realtime_gate,
        },
        remarks="V1 API production observation metadata",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed.metadata["phase_b_production_observation"] == production_observation


def _write_learning_signal(learning_service, suffix: str) -> None:
    record = learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind="experience_candidate",
        trace_id=f"api-lsm-learning-{suffix}",
        detail={
            "source": "api_living_self_model_test",
            "candidate_version": "phase-c-experience-candidate-v1",
            "candidate_id": f"api-lsm-candidate-{suffix}",
            "task_id": f"api-lsm-task-{suffix}",
            "candidate": {"candidate_id": f"api-lsm-candidate-{suffix}", "task_id": f"api-lsm-task-{suffix}"},
        },
    )
    rows = learning_service.query_overall_records(limit=20, trace_id=record.trace_id)
    assert len([row for row in rows if row.detail.get("candidate_id") == f"api-lsm-candidate-{suffix}"]) == 1


@pytest.mark.asyncio
async def test_q8_phase_b_production_observation_api_uses_real_requests_and_business_fields(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-production-api-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 3),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 3
    tasks.sort(key=lambda task: task.title)
    for index, task in enumerate(tasks):
        await _complete_good(acceptance_app.state.task_service, task)
        await _write_production_metadata(acceptance_app.state.task_service, task, suffix, index)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/production-observation-gate",
            params={
                "session_id": session_id,
                "expected_task_count": 3,
                "minimum_production_history_count": 3,
                "minimum_manual_label_count": 3,
                "minimum_observation_days": 3,
            },
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["production_observation_gate_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["production_history_count"] == 3
    assert payload["manual_label_count"] == 3
    assert payload["observation_day_count"] == 3
    assert payload["decision_counts"] == {"accept": 3, "downgrade": 0, "reject": 0}
    assert {receipt["task_id"] for receipt in payload["receipts"]} == {task.task_id for task in tasks}
    assert all(receipt["production_evidence"] for receipt in payload["receipts"])


@pytest.mark.asyncio
async def test_q8_phase_m_living_self_model_api_uses_real_requests_and_fails_closed(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-m-api-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _complete_good(acceptance_app.state.task_service, task)
    _write_learning_signal(acceptance_app.state.learning_service, suffix)

    with _live_http_server(acceptance_app) as base_url:
        ok_response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-m/living-self-model",
            params={"session_id": session_id, "expected_task_count": 1, "minimum_signal_count": 2},
            timeout=10,
        )
        missing_response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-m/living-self-model",
            params={"session_id": f"{session_id}-missing", "expected_task_count": 1, "minimum_signal_count": 2},
            timeout=10,
        )

    assert ok_response.status_code == 200
    payload = ok_response.json()
    assert payload["living_self_model_status"] == "ready"
    assert payload["session_id"] == session_id
    assert payload["observed_task_count"] == 1
    assert payload["success_count"] == 1
    assert payload["living_self_model"]["success_rate"] == 1.0
    assert payload["confidence_drift_indicator"]["drift_count"] == 0

    assert missing_response.status_code == 409
    detail = missing_response.json()["detail"]
    assert detail["error"] == "q8_phase_m_living_self_model_failed"
    assert detail["session_id"] == f"{session_id}-missing"
    assert {"reason": "task_count_mismatch", "expected": 1, "actual": 0} in detail["failures"]
