from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service
from zentex.reflection.living_self_model import (
    LivingSelfModelError,
    build_living_self_model_report,
    record_living_self_model_snapshot,
)


def _snapshot(session_id: str, suffix: str) -> dict:
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-m-lsm-{suffix}",
            "summary": "Q8 Phase M LivingSelfModel test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase m living self model {suffix}",
                    "primary_objectives": ["derive living self model from real outcomes"],
                    "secondary_objectives": ["track weakness patterns and confidence drift"],
                    "completion_conditions": ["living self model snapshot is queryable"],
                    "pause_conditions": ["task outcome missing"],
                    "escalation_conditions": ["confidence drift detected"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"phase-m-lsm-success-{suffix}",
                            "title": f"phase m living self model success {suffix}",
                            "priority": "high",
                            "success_criteria": ["actual outcome captured", "evidence captured"],
                            "acceptance_conditions": ["self model records strength"],
                            "expected_outcome": {"kind": "success", "session_id": session_id},
                            "risk_assessment": {"risk_level": "medium"},
                        },
                        {
                            "task_id": f"phase-m-lsm-failure-{suffix}",
                            "title": f"phase m living self model failure {suffix}",
                            "priority": "high",
                            "success_criteria": ["actual outcome captured", "evidence captured"],
                            "acceptance_conditions": ["self model records weakness"],
                            "expected_outcome": {"kind": "failure", "session_id": session_id},
                            "risk_assessment": {"risk_level": "medium"},
                        },
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


async def _complete_success(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {"kind": "success", "task_id": task.task_id},
            "evidence": [f"phase m success evidence {task.task_id}"],
        },
        remarks="phase m living self model success",
    )
    assert completed["success"] is True
    outcome = task_service.get_task_outcome(task.task_id)
    assert outcome["overall_passed"] is True
    assert outcome["confidence_score"] == 1.0


async def _complete_failure(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={"actual_outcome": {"kind": "failure", "task_id": task.task_id}},
        remarks="phase m living self model failure",
    )
    assert completed["success"] is False
    outcome = task_service.get_task_outcome(task.task_id)
    assert outcome["overall_passed"] is False
    assert outcome["confidence_score"] < 1.0


def _write_all_outcome_channels(real_ci_runtime, task_id: str) -> None:
    reflection = real_ci_runtime.task_service.write_task_outcome_to_reflection(
        real_ci_runtime.reflection_service,
        task_id,
    )
    memory = real_ci_runtime.task_service.write_task_outcome_to_memory(
        real_ci_runtime.memory_service,
        task_id,
    )
    learning = real_ci_runtime.task_service.write_task_outcome_to_learning(
        real_ci_runtime.learning_service,
        task_id,
    )
    queried = real_ci_runtime.task_service.get_task_outcome(task_id)
    assert queried["reflection_id"] == reflection["reflection_id"]
    assert queried["memory_id"] == memory["memory_id"]
    assert queried["learning_trace_id"] == learning["learning_trace_id"]


@pytest.mark.asyncio
async def test_living_self_model_records_real_strength_weakness_and_confidence_drift(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"phase-m-lsm-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    tasks.sort(key=lambda task: task.title)
    failure_task, success_task = tasks[0], tasks[1]

    await _complete_failure(real_ci_runtime.task_service, failure_task)
    await _complete_success(real_ci_runtime.task_service, success_task)
    _write_all_outcome_channels(real_ci_runtime, failure_task.task_id)
    _write_all_outcome_channels(real_ci_runtime, success_task.task_id)

    report = build_living_self_model_report(
        task_service=real_ci_runtime.task_service,
        learning_service=real_ci_runtime.learning_service,
        session_id=session_id,
        expected_task_count=2,
    )

    assert report["living_self_model_status"] == "ready"
    assert report["observed_task_count"] == 2
    assert report["success_count"] == 1
    assert report["failure_count"] == 1
    assert report["living_self_model"]["success_rate"] == 0.5
    assert report["recent_weakness_patterns"] == [{"pattern": "q8_required_outcome_evidence", "count": 1}]
    by_task = {receipt["task_id"]: receipt for receipt in report["receipts"]}
    assert by_task[success_task.task_id]["overall_passed"] is True
    assert by_task[failure_task.task_id]["weakness_signals"] == ["q8_required_outcome_evidence"]
    assert report["confidence_drift_indicator"]["drift_count"] == 0

    snapshot = record_living_self_model_snapshot(
        task_service=real_ci_runtime.task_service,
        learning_service=real_ci_runtime.learning_service,
        session_id=session_id,
        expected_task_count=2,
    )
    assert snapshot["living_self_model_snapshot_status"] == "recorded"
    rows = real_ci_runtime.learning_service.query_overall_records(
        limit=20,
        trace_id=snapshot["learning_trace_id"],
    )
    matching = [row for row in rows if row.detail.get("session_id") == session_id]
    assert len(matching) == 1
    assert matching[0].detail["recent_weakness_patterns"] == report["recent_weakness_patterns"]


@pytest.mark.asyncio
async def test_living_self_model_fails_closed_when_real_outcome_is_missing(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"phase-m-lsm-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    await _complete_success(real_ci_runtime.task_service, tasks[0])

    with pytest.raises(LivingSelfModelError) as exc_info:
        build_living_self_model_report(
            task_service=real_ci_runtime.task_service,
            learning_service=real_ci_runtime.learning_service,
            session_id=session_id,
            expected_task_count=2,
        )

    reasons = [failure["reason"] for failure in exc_info.value.failures]
    assert "task_outcome_missing" in reasons
