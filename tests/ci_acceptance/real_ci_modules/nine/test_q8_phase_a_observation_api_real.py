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
        "role_context": "phase a api observer",
        "resource_context": "real acceptance app task service",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.5,
            "continuity": 0.2,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "api_evidence_first",
        "action_rhythm_hint": "api_confirm_before_commit",
    }
    return {
        "trace_id": f"trace-q9-phase-a-api-{suffix}",
        "summary": "Q9 Phase A API observation profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, *, include_q9: bool = True) -> dict:
    snapshot = {
        "q8": {
            "trace_id": f"trace-q8-phase-a-api-{suffix}",
            "summary": "Q8 Phase A observation API test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"observe phase a API {suffix}",
                    "primary_objectives": ["observe q9 evaluation effects through API"],
                    "secondary_objectives": ["preserve phase a metadata"],
                    "completion_conditions": ["phase a API observation report is exact"],
                    "pause_conditions": ["phase a metadata missing"],
                    "escalation_conditions": ["priority decision mismatch"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"phase-a-api-risk-{suffix}",
                            "title": f"phase a API high risk task {suffix}",
                            "priority": "medium",
                            "success_criteria": ["risk controlled with evidence"],
                            "risk_assessment": {"risk_level": "high"},
                        }
                    ],
                    "blocked_self_tasks": [
                        {
                            "task_id": f"phase-a-api-base-{suffix}",
                            "title": f"phase a API base priority task {suffix}",
                            "priority": "low",
                            "success_criteria": ["base priority preserved"],
                            "risk_assessment": {"risk_level": "low"},
                        }
                    ],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }
    if include_q9:
        snapshot["q9"] = _q9_snapshot(suffix)
    return snapshot


def _lens_snapshot(session_id: str, suffix: str, lens: str) -> dict:
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    weights = {item: 0.1 for item in required_lenses}
    weights[lens] = 0.7
    evaluation_profile = {
        "role_context": f"phase a API {lens} observer",
        "resource_context": "real acceptance app lens distribution",
        "risk_level": "high" if lens == "risk_control" else "low",
        "evaluation_weights": weights,
        "conservative_mode_triggered": False,
        "evaluation_style": f"api_{lens}_dominant",
        "action_rhythm_hint": "api_confirm_lens_distribution",
    }
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-a-api-lens-{lens}-{suffix}",
            "summary": f"Q8 Phase A API {lens} lens distribution test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"observe phase a API {lens} lens {suffix}",
                    "primary_objectives": [f"activate API {lens} lens"],
                    "secondary_objectives": ["preserve lens metadata"],
                    "completion_conditions": ["phase a API lens distribution is exact"],
                    "pause_conditions": ["lens metadata missing"],
                    "escalation_conditions": ["lens distribution unhealthy"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"phase-a-api-lens-{lens}-{suffix}",
                            "title": f"phase a API {lens} lens task {suffix}",
                            "priority": "low",
                            "success_criteria": [f"{lens} lens is represented"],
                            "risk_assessment": {
                                "risk_level": "high" if lens == "risk_control" else "low",
                            },
                        }
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        },
        "q9": {
            "trace_id": f"trace-q9-phase-a-api-lens-{lens}-{suffix}",
            "summary": f"Q9 Phase A API {lens} lens profile",
            "context_updates": {
                "q9_evaluation_profile": evaluation_profile,
                "q9_action_posture": {"evaluation_profile": evaluation_profile},
            },
            "result": {"evaluation_profile": evaluation_profile},
        },
    }


async def _write_manual_reviews(task_service, tasks, suffix: str, *, obvious_drift: bool = False) -> None:
    for index, task in enumerate(tasks):
        review = {
            "review_status": "completed",
            "reviewer_id": f"phase-a-api-reviewer-{suffix}",
            "reviewed_at": f"2026-04-28T11:{index:02d}:00+08:00",
            "task_quality_label": "good" if not obvious_drift else "bad",
            "obvious_drift": obvious_drift,
        }
        await task_service.update_task_metadata(
            task.task_id,
            {"phase_a_manual_review": review},
            remarks="Phase A API manual review evidence recorded by real test.",
        )
        refreshed = task_service.get_task(task.task_id)
        assert refreshed is not None
        assert refreshed.metadata["phase_a_manual_review"] == review


async def _write_open_quality_issue(task_service, task, suffix: str) -> dict:
    issue = {
        "issue_id": f"phase-a-api-p1-quality-{suffix}",
        "issue_type": "task_quality",
        "severity": "p1",
        "status": "open",
        "summary": "manual review found API task quality regression",
    }
    await task_service.update_task_metadata(
        task.task_id,
        {"phase_a_quality_issue": issue},
        remarks="Phase A API P1 task quality issue recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_a_quality_issue"] == issue
    return issue


@pytest.mark.asyncio
async def test_q8_phase_a_observation_api_returns_exact_real_priority_report(acceptance_app: FastAPI) -> None:
    """查询 API：真实同步 Q8/Q9 后，HTTP 返回必须精确反映 Phase A 业务优先级决策。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    assert {task.priority.value for task in tasks} == {"high", "low"}

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-observation",
            params={"session_id": session_id, "expected_task_count": 2},
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["observation_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["observed_task_count"] == 2
    assert payload["priority_counts"] == {"high": 1, "low": 1}
    assert payload["queue_counts"] == {"blocked_self_tasks": 1, "next_self_tasks": 1}
    assert payload["applied_rule_counts"] == {
        "base_q8_priority": 1,
        "risk_control_high_risk_to_high": 1,
    }
    assert payload["q9_trace_counts"] == {f"trace-q9-phase-a-api-{suffix}": 2}
    assert payload["average_evaluation_weights"] == {
        "accuracy": 0.25,
        "continuity": 0.2,
        "risk_control": 0.5,
        "speed": 0.05,
    }
    receipts_by_title = {receipt["title"]: receipt for receipt in payload["receipts"]}
    risk_receipt = receipts_by_title[f"phase a API high risk task {suffix}"]
    assert risk_receipt["final_priority"] == "high"
    assert risk_receipt["actual_priority"] == "high"
    assert risk_receipt["applied_rules"] == ["risk_control_high_risk_to_high"]
    assert risk_receipt["q9_trace_id"] == f"trace-q9-phase-a-api-{suffix}"
    base_receipt = receipts_by_title[f"phase a API base priority task {suffix}"]
    assert base_receipt["final_priority"] == "low"
    assert base_receipt["actual_priority"] == "low"
    assert base_receipt["applied_rules"] == ["base_q8_priority"]


@pytest.mark.asyncio
async def test_q8_phase_a_observation_api_returns_409_when_phase_a_metadata_is_not_ready(
    acceptance_app: FastAPI,
) -> None:
    """异常 API：Q9 缺失导致 Phase A 未 ready 时，必须 409 并返回真实 task_id。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, include_q9=False),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    assert {task.metadata["phase_a_evaluation"]["status"] for task in tasks} == {"missing"}

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-observation",
            params={"session_id": session_id, "expected_task_count": 2},
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_a_observation_failed"
    assert detail["session_id"] == session_id
    reasons = [failure["reason"] for failure in detail["failures"]]
    assert reasons.count("phase_a_evaluation_not_ready") == 2
    assert reasons.count("q9_trace_id_missing") == 2
    assert reasons.count("applied_rules_missing") == 2
    assert reasons.count("evaluation_weight_missing") == 6
    assert sorted(
        failure["field"]
        for failure in detail["failures"]
        if failure["reason"] == "evaluation_weight_missing"
    ) == [
        "accuracy",
        "accuracy",
        "continuity",
        "continuity",
        "risk_control",
        "risk_control",
    ]
    assert {failure["task_id"] for failure in detail["failures"]} == {task.task_id for task in tasks}


@pytest.mark.asyncio
async def test_q8_phase_a_lens_distribution_api_returns_exact_real_lens_report(
    acceptance_app: FastAPI,
) -> None:
    """查询 API：真实同步五类 EvaluationProfile lens 后，HTTP 返回必须精确反映主导 lens 分布。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-lens-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=acceptance_app.state.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    assert {task.metadata["phase_a_evaluation"]["evaluation_style"] for task in tasks} == {
        f"api_{lens}_dominant" for lens in required_lenses
    }

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-lens-distribution",
            params={
                "session_id": session_id,
                "expected_task_count": 5,
                "required_lenses": ",".join(required_lenses),
            },
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["lens_distribution_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["observed_task_count"] == 5
    assert payload["required_lenses"] == list(required_lenses)
    assert payload["lens_activation_counts"] == {lens: 1 for lens in required_lenses}
    assert payload["lens_positive_counts"] == {lens: 5 for lens in required_lenses}
    assert payload["dominant_lens_coverage_ratio"] == 1.0
    assert payload["task_status_counts"] == {"archived": 4, "todo": 1}

    receipts_by_lens = {receipt["dominant_lenses"][0]: receipt for receipt in payload["receipts"]}
    assert set(receipts_by_lens) == set(required_lenses)
    for lens in required_lenses:
        receipt = receipts_by_lens[lens]
        assert receipt["evaluation_weights"][lens] == 0.7
        assert receipt["q9_trace_id"] == f"trace-q9-phase-a-api-lens-{lens}-{suffix}"


@pytest.mark.asyncio
async def test_q8_phase_a_lens_distribution_api_returns_409_for_unactivated_lenses(
    acceptance_app: FastAPI,
) -> None:
    """异常 API：只激活一个主导 lens 时必须 409，并返回未激活 lens 明细。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-lens-missing-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_lens_snapshot(session_id, suffix, "risk_control"),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 1
    assert tasks[0].metadata["phase_a_evaluation"]["evaluation_weights"]["risk_control"] == 0.7

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-lens-distribution",
            params={
                "session_id": session_id,
                "expected_task_count": 1,
                "required_lenses": ",".join(required_lenses),
            },
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_a_lens_distribution_failed"
    assert detail["session_id"] == session_id
    assert {
        failure["lens"] for failure in detail["failures"] if failure["reason"] == "required_lens_not_activated"
    } == {"accuracy", "continuity", "speed", "creativity"}
    assert all(failure["reason"] != "lens_weight_missing" for failure in detail["failures"])


@pytest.mark.asyncio
async def test_q8_phase_a_observation_gate_api_returns_exact_real_gate_report(
    acceptance_app: FastAPI,
) -> None:
    """门禁 API：真实任务、真实人工抽查 metadata、真实 HTTP 请求必须共同通过 Phase A 观测门禁。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-gate-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=acceptance_app.state.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    await _write_manual_reviews(acceptance_app.state.task_service, tasks, suffix)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-observation-gate",
            params={
                "session_id": session_id,
                "expected_task_count": 5,
                "required_lenses": ",".join(required_lenses),
                "minimum_manual_reviews": 5,
                "max_weight_delta": 0.75,
                "max_obvious_drift_rate": 0,
            },
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["observation_gate_status"] == "passed"
    assert payload["session_id"] == session_id
    assert payload["lens_distribution"]["lens_activation_counts"] == {lens: 1 for lens in required_lenses}
    assert payload["weight_trend"]["max_weight_delta_observed"] == 0.6
    assert payload["weight_trend"]["shift_count"] == 4
    assert payload["manual_review"]["reviewed_count"] == 5
    assert payload["manual_review"]["obvious_drift_count"] == 0
    assert len(payload["manual_review"]["receipts"]) == 5


@pytest.mark.asyncio
async def test_q8_phase_a_observation_gate_api_returns_409_for_manual_review_drift(
    acceptance_app: FastAPI,
) -> None:
    """异常门禁 API：真实写入 obvious_drift 后，HTTP 必须 409 并返回漂移率失败原因。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-gate-review-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map=_lens_snapshot(session_id, suffix, "risk_control"),
    )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 1
    await _write_manual_reviews(acceptance_app.state.task_service, tasks, suffix, obvious_drift=True)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-observation-gate",
            params={
                "session_id": session_id,
                "expected_task_count": 1,
                "required_lenses": "risk_control",
                "minimum_manual_reviews": 1,
                "max_obvious_drift_rate": 0,
            },
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_a_observation_gate_failed"
    assert detail["session_id"] == session_id
    assert detail["failures"] == [
        {
            "reason": "manual_review_obvious_drift_rate_too_high",
            "obvious_drift_rate": 1.0,
            "max_allowed": 0.0,
        }
    ]


@pytest.mark.asyncio
async def test_q8_phase_a_exit_gate_api_allows_phase_b_skip_after_real_gate(
    acceptance_app: FastAPI,
) -> None:
    """退出门禁 API：Phase A 观测门禁通过且无 P1 质量问题时，真实 HTTP 返回允许跳过 Phase B。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-exit-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=acceptance_app.state.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    await _write_manual_reviews(acceptance_app.state.task_service, tasks, suffix)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-exit-gate",
            params={
                "session_id": session_id,
                "expected_task_count": 5,
                "required_lenses": ",".join(required_lenses),
                "minimum_manual_reviews": 5,
                "max_weight_delta": 0.75,
                "max_obvious_drift_rate": 0,
            },
            timeout=10,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase_a_exit_status"] == "passed"
    assert payload["phase_b_skip_allowed"] is True
    assert payload["phase_b_required"] is False
    assert payload["quality_issues"]["open_p1_quality_issue_count"] == 0
    assert payload["observation_gate"]["manual_review"]["reviewed_count"] == 5


@pytest.mark.asyncio
async def test_q8_phase_a_exit_gate_api_returns_409_when_real_p1_quality_issue_is_open(
    acceptance_app: FastAPI,
) -> None:
    """退出门禁 API：真实写入开放 P1 task quality issue 后，HTTP 必须 409 并要求进入 Phase B。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-a-api-exit-p1-{suffix}"
    required_lenses = ("accuracy", "risk_control", "continuity", "speed", "creativity")
    for lens in required_lenses:
        await sync_q8_tasks_to_task_service(
            task_service=acceptance_app.state.task_service,
            session_id=session_id,
            snapshot_map=_lens_snapshot(session_id, suffix, lens),
        )
    tasks = acceptance_app.state.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 5
    await _write_manual_reviews(acceptance_app.state.task_service, tasks, suffix)
    issue = await _write_open_quality_issue(acceptance_app.state.task_service, tasks[0], suffix)

    with _live_http_server(acceptance_app) as base_url:
        response = requests.get(
            f"{base_url}/api/web/nine-questions/q8/phase-a-exit-gate",
            params={
                "session_id": session_id,
                "expected_task_count": 5,
                "required_lenses": ",".join(required_lenses),
                "minimum_manual_reviews": 5,
                "max_weight_delta": 0.75,
                "max_obvious_drift_rate": 0,
            },
            timeout=10,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "q8_phase_a_exit_gate_failed"
    assert detail["session_id"] == session_id
    assert detail["phase_b_required"] is True
    assert detail["phase_b_skip_allowed"] is False
    assert detail["failures"] == [
        {
            "reason": "phase_a_open_p1_quality_issue_limit_exceeded",
            "open_p1_quality_issue_count": 1,
            "max_allowed": 0,
        }
    ]
    refreshed = acceptance_app.state.task_service.get_task(tasks[0].task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_a_quality_issue"] == issue
