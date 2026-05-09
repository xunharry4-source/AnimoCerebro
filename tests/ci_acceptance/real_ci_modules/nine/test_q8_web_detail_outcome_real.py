from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


@pytest.mark.asyncio
async def test_q8_web_detail_exposes_real_task_contract_and_outcome(acceptance_app: FastAPI) -> None:
    """查询链路：Q8 detail API 必须返回真实同步任务、验收契约和 task_outcomes。"""
    suffix = unique_suffix()
    session_id = acceptance_app.state.session.session_id
    trace_id = f"q8-web-outcome-{suffix}"
    task_title = f"web exposes verified q8 outcome {suffix}"
    objective = {
        "current_mission": f"ship q8 web detail {suffix}",
        "primary_objectives": ["show objective profile"],
        "secondary_objectives": ["show verification evidence"],
        "completion_conditions": ["web detail contains task outcome"],
        "pause_conditions": ["missing q8 task outcome"],
        "escalation_conditions": ["verification failed"],
        "current_phase_tasks": [task_title],
        "priority_order": [task_title],
    }
    task_queue = {
        "next_self_tasks": [
            {
                "task_id": f"q8-web-task-{suffix}",
                "title": task_title,
                "priority": "high",
                "expected_outcome": {"web": "q8_detail"},
                "success_criteria": ["actual outcome captured", "evidence captured"],
                "acceptance_conditions": ["task_outcome.overall_passed is true"],
                "verification_method": "rule_based_web_detail",
                "risk_assessment": {"risk_level": "low"},
            }
        ],
        "blocked_self_tasks": [],
        "proactive_actions": [],
    }
    snapshot = {
        "tool_id": "nine_question_q8_decision",
        "summary": "Q8 web detail outcome test",
        "confidence": 0.93,
        "trace_id": trace_id,
        "result": {"objective": objective, "task_queue": task_queue},
        "context_updates": {
            "q8_objective_profile": objective,
            "q8_task_queue": task_queue,
            "q8_objective_and_queue": {"objective": objective, "task_queue": task_queue},
        },
    }

    await acceptance_app.state.nine_question_service.persist_question_snapshot_patch(
        "q8",
        snapshot,
        refresh_reason="q8_web_detail_outcome_real",
    )
    await sync_q8_tasks_to_task_service(
        task_service=acceptance_app.state.task_service,
        session_id=session_id,
        snapshot_map={"q8": snapshot},
    )
    synced = acceptance_app.state.task_service.list_tasks(
        metadata_filters={"source": "nine_questions.q8", "session_id": session_id, "trace_id": trace_id}
    )
    assert len(synced) == 1, "Q8 snapshot 同步后必须能查询到唯一真实任务"
    task = synced[0]
    assert task.title == task_title
    assert task.contract.success_criteria == ["actual outcome captured", "evidence captured"]

    completed = await acceptance_app.state.task_service.complete_task_with_verification(
        task.task_id,
        result={"actual_outcome": {"web": "q8_detail"}, "evidence": ["real web detail receipt"]},
        remarks="web detail real outcome",
    )
    assert completed["success"] is True
    persisted_outcome = acceptance_app.state.task_service.get_task_outcome(task.task_id)
    assert persisted_outcome is not None, "完成任务后必须能查询到 task_outcomes"
    assert persisted_outcome["overall_passed"] is True

    with TestClient(acceptance_app) as client:
        response = client.get("/api/web/nine-questions/q8")

    assert response.status_code == 200
    payload = response.json()
    assert payload["question_id"] == "q8"
    assert payload["trace_id"] == trace_id
    inference = payload["inference_result"]
    objective_payload = inference["objective_profile"]
    assert objective_payload["current_primary_objective"] == objective["current_mission"]
    assert objective_payload["primary_objectives"] == ["show objective profile"]
    assert objective_payload["secondary_objectives"] == ["show verification evidence"]
    assert objective_payload["completion_conditions"] == ["web detail contains task outcome"]
    assert objective_payload["pause_conditions"] == ["missing q8 task outcome"]
    assert objective_payload["escalation_conditions"] == ["verification failed"]

    rows = inference["task_queue"]["next_self_tasks"]
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == task_title
    assert row["task_binding_status"] == "bound"
    assert row["physical_task_id"] == task.task_id
    assert row["task_status"] == "done"
    assert row["expected_outcome"] == {"web": "q8_detail"}
    assert row["success_criteria"] == ["actual outcome captured", "evidence captured"]
    assert row["acceptance_conditions"] == ["task_outcome.overall_passed is true"]
    assert row["verification_enabled"] is True
    assert row["task_outcome"]["overall_passed"] is True
    assert row["task_outcome"]["actual_outcome"] == {"web": "q8_detail"}
    assert row["task_outcome"]["verification_result"]["overall_passed"] is True
    assert row["task_outcome"]["verification_result"]["verifier_results"]
