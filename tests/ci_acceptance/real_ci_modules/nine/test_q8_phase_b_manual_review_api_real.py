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
        "role_context": "phase b manual review api",
        "resource_context": "real scorer calibration API",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.55,
            "continuity": 0.15,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "phase_b_manual_review_api",
        "action_rhythm_hint": "api_calibrate_after_real_score",
    }
    return {
        "trace_id": f"trace-q9-phase-b-manual-review-api-{suffix}",
        "summary": "Q9 Phase B manual review API profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int = 3) -> dict:
    rows = [
        {
            "task_id": f"phase-b-manual-review-api-{suffix}-{index}",
            "title": f"phase b manual review API task {suffix} #{index}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["manual review API can calibrate scoring result"],
            "expected_outcome": {"review_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-manual-review-api-{suffix}",
            "summary": "Q8 Phase B manual review API calibration test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b manual review API mission {suffix}",
                    "primary_objectives": ["calibrate Q8 value scorer with human review through API"],
                    "secondary_objectives": ["preserve API review evidence"],
                    "completion_conditions": ["manual review API coverage and agreement pass"],
                    "pause_conditions": ["missing manual review"],
                    "escalation_conditions": ["low API human agreement"],
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
                "evidence": [f"real API manual review calibration evidence for {task.task_id}"],
            },
            "evidence": [f"real API manual review calibration receipt for {task.task_id}"],
        },
        remarks="phase b manual review API source outcome",
    )
    assert completed["success"] is True
    persisted = task_service.get_task_outcome(task.task_id)
    assert persisted is not None
    assert persisted["overall_passed"] is True
    assert persisted["actual_outcome"]["evidence"]


async def _write_manual_review(
    task_service,
    task,
    suffix: str,
    index: int,
    *,
    human_label: str = "accept",
) -> dict:
    review = {
        "review_id": f"phase-b-manual-review-api-{suffix}-{index}",
        "reviewer_id": f"phase-b-api-reviewer-{suffix}",
        "reviewed_at": f"2026-04-28T17:{index:02d}:00+08:00",
        "task_id": task.task_id,
        "q8_trace_id": task.metadata["trace_id"],
        "scorer_layer": "phase_b_rule_based",
        "scorer_decision": "accept",
        "human_label": human_label,
        "review_evidence": [f"reviewed API scorer receipt and task outcome for {task.task_id}"],
    }
    await task_service.update_task_metadata(
        task.task_id,
        {"phase_b_manual_review": review},
        remarks="Phase B manual review API evidence recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_b_manual_review"] == review
    return review


@pytest.mark.asyncio
async def test_q8_phase_b_manual_review_api_returns_exact_real_calibration_report(
    acceptance_app: FastAPI,
) -> None:
    """查询 API：真实 review metadata 和真实 outcome 必须在 HTTP 返回中逐字段体现。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-manual-review-api-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 3),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 3
    for task in tasks:
        await _complete_with_good_outcome(acceptance_app.state.task_service, task)
    for index, task in enumerate(tasks[:2]):
        await _write_manual_review(acceptance_app.state.task_service, task, suffix, index)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/manual-review-calibration",
            params={
                "session_id": session_id,
                "expected_task_count": 3,
                "minimum_review_count": 2,
                "minimum_review_ratio": 0.50,
                "minimum_agreement_rate": 1.0,
            },
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["manual_review_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["task_count"] == 3
    assert payload["required_review_count"] == 2
    assert payload["reviewed_count"] == 2
    assert payload["agreement_rate"] == 1.0
    assert payload["human_label_counts"] == {"accept": 2, "downgrade": 0, "reject": 0}
    assert {receipt["task_id"] for receipt in payload["receipts"]} == {task.task_id for task in tasks[:2]}
    assert all(receipt["q8_trace_id"] == receipt_q8 for receipt, receipt_q8 in zip(payload["receipts"], [task.metadata["trace_id"] for task in tasks[:2]]))
    assert all(receipt["outcome_passed"] is True for receipt in payload["receipts"])
    assert all(receipt["agreement"] is True for receipt in payload["receipts"])


@pytest.mark.asyncio
async def test_q8_phase_b_manual_review_api_returns_409_when_review_count_is_missing(
    acceptance_app: FastAPI,
) -> None:
    """异常 API：抽查数量不足时必须 409，并返回真实 reviewed_count。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-manual-review-api-low-count-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 3),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    for task in tasks:
        await _complete_with_good_outcome(acceptance_app.state.task_service, task)
    await _write_manual_review(acceptance_app.state.task_service, tasks[0], suffix, 0)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/manual-review-calibration",
            params={
                "session_id": session_id,
                "expected_task_count": 3,
                "minimum_review_count": 2,
                "minimum_review_ratio": 0.50,
            },
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_b_manual_review_failed"
    assert detail["session_id"] == session_id
    assert detail["failures"] == [
        {
            "reason": "manual_review_count_below_required",
            "required_review_count": 2,
            "reviewed_count": 1,
        }
    ]
