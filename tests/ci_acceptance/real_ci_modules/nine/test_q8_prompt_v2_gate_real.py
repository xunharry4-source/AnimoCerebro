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
from zentex.nine_questions.q8_prompt_v2_gate import (
    Q8PromptV2GateError,
    build_q8_prompt_v2_gate_report,
)
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
            "task_id": f"q8-prompt-v2-gate-{suffix}-{index:03d}",
            "title": f"q8 prompt v2 historical replay {suffix} #{index:03d}",
            "priority": "medium",
            "success_criteria": ["prompt v2 replay outcome captured", "prompt v2 metrics captured"],
            "acceptance_conditions": ["prompt v2 gate metrics are queryable after verification"],
            "expected_outcome": {"sample_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "medium"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-prompt-v2-gate-{suffix}",
            "summary": "Q8 prompt V2 gate test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"prompt v2 gate mission {suffix}",
                    "primary_objectives": ["verify Q8 prompt V2 evidence gate"],
                    "secondary_objectives": ["preserve prompt and call metrics"],
                    "completion_conditions": ["all prompt V2 replay samples pass"],
                    "pause_conditions": ["prompt V2 evidence missing"],
                    "escalation_conditions": ["quality regresses or token cost grows"],
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


def _passing_metrics(task, suffix: str, index: int) -> dict:
    return {
        "source": "production_history",
        "environment": "production",
        "sample_id": f"prod-q8-prompt-v2-{suffix}-{index:03d}",
        "q8_trace_id": task.metadata["trace_id"],
        "evidence_uri": f"production-export://q8-prompt-v2/{suffix}/{index:03d}",
        "baseline_prompt_chars": 12000,
        "current_prompt_chars": 3900,
        "baseline_llm_calls": 3,
        "current_llm_calls": 1,
        "baseline_latency_ms": 10000,
        "current_latency_ms": 5500,
        "baseline_token_cost": 6000,
        "current_token_cost": 2400,
        "baseline_quality_score": 0.82,
        "current_quality_score": 0.84,
    }


async def _complete_with_outcome(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {
                "task_id": task.task_id,
                "title": task.title,
                "q8_trace_id": task.metadata["trace_id"],
                "prompt_v2_gate_sample": True,
            },
            "evidence": [f"prompt v2 gate verification receipt for {task.task_id}"],
        },
        remarks="prompt v2 gate replay outcome",
    )
    assert completed["success"] is True
    outcome = task_service.get_task_outcome(task.task_id)
    assert outcome is not None
    assert outcome["overall_passed"] is True
    assert outcome["actual_outcome"]["task_id"] == task.task_id


async def _write_metrics(task_service, task, metrics: dict) -> None:
    await task_service.update_task_metadata(
        task.task_id,
        {"q8_prompt_v2_metrics": metrics},
        remarks="Q8 prompt V2 production-history metrics recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["q8_prompt_v2_metrics"] == metrics


async def _prepare_prompt_v2_samples(task_service, *, session_id: str, suffix: str, count: int) -> list:
    await sync_q8_tasks_to_task_service(
        task_service=task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, count),
    )
    tasks = task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == count
    tasks.sort(key=lambda task: task.title)
    for index, task in enumerate(tasks):
        await _complete_with_outcome(task_service, task)
        await _write_metrics(task_service, task, _passing_metrics(task, suffix, index))
    refreshed = task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(refreshed) == count
    assert all(task.metadata.get("q8_prompt_v2_metrics") for task in refreshed)
    assert all(task_service.get_task_outcome(task.task_id) for task in refreshed)
    return refreshed


@pytest.mark.asyncio
async def test_q8_prompt_v2_gate_passes_with_100_real_replay_samples(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"q8-prompt-v2-gate-{suffix}"
    await _prepare_prompt_v2_samples(
        real_ci_runtime.task_service,
        session_id=session_id,
        suffix=suffix,
        count=100,
    )

    report = build_q8_prompt_v2_gate_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_replay_count=100,
    )

    assert report["gate_status"] == "passed"
    assert report["phase"] == "v2_phase_0_q8_prompt_engineering"
    assert report["session_id"] == session_id
    assert report["expected_replay_count"] == 100
    assert report["replay_count"] == 100
    assert report["source_counts"] == {"production_history": 100}
    assert report["environment_counts"] == {"production": 100}
    assert report["averages"]["baseline_prompt_chars"] == 12000
    assert report["averages"]["current_prompt_chars"] == 3900
    assert report["averages"]["prompt_reduction_rate"] == 0.675
    assert report["averages"]["current_llm_calls"] == 1
    assert report["averages"]["latency_reduction_rate"] == 0.45
    assert report["averages"]["token_reduction_rate"] == 0.6
    assert report["averages"]["quality_delta"] == 0.02
    assert all(result["passed"] is True for result in report["threshold_results"].values())
    assert len(report["receipts"]) == 100
    assert all(receipt["outcome_passed"] is True for receipt in report["receipts"])
    assert all(receipt["current_prompt_chars"] <= 4000 for receipt in report["receipts"])


@pytest.mark.asyncio
async def test_q8_prompt_v2_gate_fails_closed_when_real_metrics_are_missing(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"q8-prompt-v2-gate-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _complete_with_outcome(real_ci_runtime.task_service, task)
    assert "q8_prompt_v2_metrics" not in task.metadata

    with pytest.raises(Q8PromptV2GateError) as exc_info:
        build_q8_prompt_v2_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_replay_count=1,
        )

    reasons = {failure["reason"] for failure in exc_info.value.failures}
    assert "q8_prompt_v2_metrics_missing" in reasons
    assert "q8_prompt_v2_real_replay_count_below_required" in reasons


@pytest.mark.asyncio
async def test_q8_prompt_v2_gate_fails_closed_when_thresholds_regress(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"q8-prompt-v2-gate-threshold-{suffix}"
    await _prepare_prompt_v2_samples(
        real_ci_runtime.task_service,
        session_id=session_id,
        suffix=suffix,
        count=2,
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    for index, task in enumerate(sorted(tasks, key=lambda item: item.title)):
        bad_metrics = _passing_metrics(task, suffix, index)
        bad_metrics.update(
            {
                "baseline_prompt_chars": 6000,
                "current_prompt_chars": 3900,
                "current_llm_calls": 2,
                "current_latency_ms": 9000,
                "current_token_cost": 5000,
                "current_quality_score": 0.7,
            }
        )
        await _write_metrics(real_ci_runtime.task_service, task, bad_metrics)

    with pytest.raises(Q8PromptV2GateError) as exc_info:
        build_q8_prompt_v2_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_replay_count=2,
        )

    reasons = {failure["reason"] for failure in exc_info.value.failures}
    assert "q8_prompt_v2_prompt_reduction_threshold_failed" in reasons
    assert "q8_prompt_v2_llm_call_consolidation_threshold_failed" in reasons
    assert "q8_prompt_v2_latency_reduction_threshold_failed" in reasons
    assert "q8_prompt_v2_token_reduction_threshold_failed" in reasons
    assert "q8_prompt_v2_quality_non_regression_threshold_failed" in reasons


@pytest.mark.asyncio
async def test_q8_prompt_v2_gate_api_returns_exact_real_requests_report(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    session_id = f"q8-prompt-v2-gate-api-{suffix}"
    await _prepare_prompt_v2_samples(
        acceptance_app.state.task_service,
        session_id=session_id,
        suffix=suffix,
        count=5,
    )

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/prompt-v2-gate",
            params={"session_id": session_id, "expected_replay_count": 5},
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["gate_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["replay_count"] == 5
    assert payload["source_counts"] == {"production_history": 5}
    assert payload["environment_counts"] == {"production": 5}
    assert payload["averages"]["prompt_reduction_rate"] == 0.675
    assert payload["threshold_results"]["llm_call_consolidation"] == {
        "passed": True,
        "actual": 1.0,
        "required": 1.2,
    }
    assert {receipt["sample_id"] for receipt in payload["receipts"]} == {
        f"prod-q8-prompt-v2-{suffix}-{index:03d}"
        for index in range(5)
    }


@pytest.mark.asyncio
async def test_q8_prompt_v2_gate_api_returns_409_when_evidence_is_missing(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    session_id = f"q8-prompt-v2-gate-api-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _complete_with_outcome(acceptance_app.state.task_service, task)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/prompt-v2-gate",
            params={"session_id": session_id, "expected_replay_count": 1},
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_prompt_v2_gate_failed"
    assert detail["session_id"] == session_id
    assert {"reason": "q8_prompt_v2_metrics_missing", "task_id": task.task_id} in detail["failures"]
