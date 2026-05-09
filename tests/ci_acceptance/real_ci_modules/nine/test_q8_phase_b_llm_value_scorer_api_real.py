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
        "role_context": "phase b llm api scorer",
        "resource_context": "real semantic value API scoring",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.55,
            "continuity": 0.15,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "phase_b_llm_api_scoring",
        "action_rhythm_hint": "api_llm_score_edge_case_after_real_outcome",
    }
    return {
        "trace_id": f"trace-q9-phase-b-llm-api-score-{suffix}",
        "summary": "Q9 Phase B LLM API score profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int = 1) -> dict:
    rows = [
        {
            "task_id": f"phase-b-llm-api-score-{suffix}-{index}",
            "title": f"phase b LLM API value score task {suffix} #{index}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["semantic API scorer can verify concrete user value"],
            "expected_outcome": {
                "score_index": index,
                "session_id": session_id,
                "user_value": "documented reduction in user verification effort",
            },
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-llm-api-score-{suffix}",
            "summary": "Q8 Phase B LLM API scoring test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b LLM API scoring mission {suffix}",
                    "primary_objectives": ["score semantic value for Q8 edge tasks through API"],
                    "secondary_objectives": ["preserve independent LLM API evidence"],
                    "completion_conditions": ["LLM API value score is recorded"],
                    "pause_conditions": ["missing task outcome"],
                    "escalation_conditions": ["LLM API scorer rejects edge task"],
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
                "evidence": [
                    f"real semantic API value evidence for {task.task_id}",
                    "user verification steps reduced from manual checklist to one scored API receipt",
                ],
                "user_value": "The API caller can decide whether the Q8 task is useful without re-reading raw logs.",
            },
            "evidence": [f"real phase b LLM API scoring receipt for {task.task_id}"],
        },
        remarks="phase b LLM API value scoring source outcome",
    )
    assert completed["success"] is True
    persisted = task_service.get_task_outcome(task.task_id)
    assert persisted is not None
    assert persisted["overall_passed"] is True
    assert persisted["actual_outcome"]["evidence"]


async def _mark_llm_review_required(task_service, task, suffix: str) -> dict:
    marker = {
        "required": True,
        "source": "phase_b_rule_api_edge_case",
        "reason": "rule score confidence was borderline and requires independent semantic API review",
        "marked_by": f"phase-b-llm-api-test-{suffix}",
    }
    await task_service.update_task_metadata(
        task.task_id,
        {"phase_b_llm_review": marker},
        remarks="Phase B LLM API edge review marker recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_b_llm_review"] == marker
    return marker


@pytest.mark.asyncio
async def test_q8_phase_b_llm_value_score_api_calls_real_ollama_and_returns_business_receipt(
    acceptance_app: FastAPI,
) -> None:
    """查询 API：通过 requests 调用真实 HTTP endpoint，并触发真实 Ollama 评分。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-llm-api-score-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _mark_llm_review_required(acceptance_app.state.task_service, task, suffix)
    await _complete_with_good_outcome(acceptance_app.state.task_service, task)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/llm-value-score",
            params={
                "session_id": session_id,
                "expected_task_count": 1,
                "expected_review_count": 1,
                "generation_provider_key": "acceptance-provider",
                "scoring_provider_key": "ollama",
                "scoring_model": "deepseek-r1:14b",
                "sample_count": 1,
                "minimum_semantic_score": 0.50,
                "minimum_confidence": 0.30,
            },
            timeout=90,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["value_score_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["scorer_layer"] == "phase_b_llm"
    assert payload["generation_provider_key"] == "acceptance-provider"
    assert payload["scoring_provider_key"] == "ollama"
    assert payload["scoring_model"] == "deepseek-r1:14b"
    assert payload["reviewed_task_count"] == 1
    receipt = payload["receipts"][0]
    assert receipt["task_id"] == task.task_id
    assert receipt["q8_trace_id"] == task.metadata["trace_id"]
    assert receipt["q9_trace_id"] == task.metadata["phase_a_evaluation"]["source_trace_id"]
    assert receipt["provider_key"] == "ollama"
    assert receipt["model"] == "deepseek-r1:14b"
    assert receipt["outcome_passed"] is True
    assert 0.0 <= receipt["semantic_score"] <= 1.0
    assert receipt["semantic_score"] >= 0.50
    assert 0.0 <= receipt["confidence"] <= 1.0
    assert receipt["confidence"] >= 0.30
    assert receipt["decision"] in {"accept", "downgrade"}
    assert len(receipt["samples"]) == 1


@pytest.mark.asyncio
async def test_q8_phase_b_llm_value_score_api_returns_409_when_provider_is_not_isolated(
    acceptance_app: FastAPI,
) -> None:
    """异常 API：评分和生成 provider 相同必须 409，不能调用同模型自评。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-llm-api-same-provider-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    await _mark_llm_review_required(acceptance_app.state.task_service, task, suffix)
    await _complete_with_good_outcome(acceptance_app.state.task_service, task)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-b/llm-value-score",
            params={
                "session_id": session_id,
                "expected_task_count": 1,
                "expected_review_count": 1,
                "generation_provider_key": "ollama",
                "scoring_provider_key": "ollama",
                "scoring_model": "deepseek-r1:14b",
                "sample_count": 1,
            },
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_b_llm_value_scoring_failed"
    assert detail["session_id"] == session_id
    assert detail["failures"] == [
        {"reason": "llm_scorer_not_isolated_from_generation", "provider_key": "ollama"}
    ]
