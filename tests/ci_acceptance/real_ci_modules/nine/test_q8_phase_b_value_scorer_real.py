from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_phase_b_value_scorer import (
    Q8PhaseBValueScoringError,
    build_q8_phase_b_value_score_report,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _q9_snapshot(suffix: str) -> dict:
    evaluation_profile = {
        "role_context": "phase b rule scorer",
        "resource_context": "real task outcome scoring",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.55,
            "continuity": 0.15,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "phase_b_rule_scoring",
        "action_rhythm_hint": "score_after_real_outcome",
    }
    return {
        "trace_id": f"trace-q9-phase-b-score-{suffix}",
        "summary": "Q9 Phase B score profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int = 2) -> dict:
    rows = [
        {
            "task_id": f"phase-b-score-{suffix}-{index}",
            "title": f"phase b value score task {suffix} #{index}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["value score can verify outcome quality"],
            "expected_outcome": {"score_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-score-{suffix}",
            "summary": "Q8 Phase B scoring test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b scoring mission {suffix}",
                    "primary_objectives": ["score real q8 task outcomes"],
                    "secondary_objectives": ["preserve scoring evidence"],
                    "completion_conditions": ["all value score dimensions pass"],
                    "pause_conditions": ["missing task outcome"],
                    "escalation_conditions": ["low value score"],
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
                "evidence": [f"real phase b scoring evidence for {task.task_id}"],
            },
            "evidence": [f"real phase b scoring receipt for {task.task_id}"],
        },
        remarks="phase b value scoring receipt",
    )
    assert completed["success"] is True
    persisted = task_service.get_task_outcome(task.task_id)
    assert persisted is not None
    assert persisted["overall_passed"] is True
    assert persisted["actual_outcome"]["task_id"] == task.task_id
    assert persisted["actual_outcome"]["evidence"]


@pytest.mark.asyncio
async def test_q8_phase_b_value_scorer_reports_exact_real_rule_scores(real_ci_runtime) -> None:
    """查询链路：Phase B 规则评分必须基于真实 Q8 任务与真实 task_outcomes。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-score-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 2),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    assert all(task.priority.value == "high" for task in tasks)
    for task in tasks:
        await _complete_with_good_outcome(real_ci_runtime.task_service, task)

    report = build_q8_phase_b_value_score_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=2,
        minimum_overall_score=0.75,
    )

    assert report["value_score_status"] == "passed"
    assert report["session_id"] == session_id
    assert report["scorer_layer"] == "phase_b_rule_based"
    assert report["scored_task_count"] == 2
    assert report["average_overall_score"] == 1.0
    assert report["average_dimension_scores"] == {
        "evidence_completeness": 1.0,
        "lens_activation": 1.0,
        "outcome_verification": 1.0,
        "risk_control_alignment": 1.0,
    }
    assert report["dominant_lens_counts"] == {"accuracy": 0, "risk_control": 2, "continuity": 0}
    assert len(report["receipts"]) == 2
    assert all(receipt["overall_score"] == 1.0 for receipt in report["receipts"])
    assert all(receipt["dimension_failures"] == {
        "outcome_verification": [],
        "evidence_completeness": [],
        "risk_control_alignment": [],
        "lens_activation": [],
    } for receipt in report["receipts"])


@pytest.mark.asyncio
async def test_q8_phase_b_value_scorer_fails_when_real_outcome_is_missing(real_ci_runtime) -> None:
    """异常链路：任务没有真实 task_outcome 时，评分必须 fail-closed，不返回空评分。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-score-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    assert real_ci_runtime.task_service.get_task_outcome(task.task_id) is None

    with pytest.raises(Q8PhaseBValueScoringError) as exc_info:
        build_q8_phase_b_value_score_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=1,
        )

    assert exc_info.value.failures == [{"reason": "task_outcome_missing", "task_id": task.task_id}]


@pytest.mark.asyncio
async def test_q8_phase_b_value_scorer_fails_on_real_failed_verification_and_low_score(real_ci_runtime) -> None:
    """异常链路：真实 verification 失败 outcome 必须导致维度失败和低分失败。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-score-low-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    completed = await real_ci_runtime.task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {
                "task_id": task.task_id,
                "title": task.title,
                "q8_trace_id": task.metadata["trace_id"],
            }
        },
        remarks="phase b low score source outcome",
    )
    assert completed["success"] is False
    persisted = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert persisted is not None
    assert persisted["overall_passed"] is False

    with pytest.raises(Q8PhaseBValueScoringError) as exc_info:
        build_q8_phase_b_value_score_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=1,
            minimum_overall_score=0.75,
        )

    reasons = [failure["reason"] for failure in exc_info.value.failures]
    assert reasons == ["phase_b_task_dimension_failed", "phase_b_task_score_below_threshold"]
    dimension_failure = exc_info.value.failures[0]
    assert dimension_failure["task_id"] == task.task_id
    assert dimension_failure["failed_dimensions"] == ["outcome_verification", "evidence_completeness"]
    assert dimension_failure["dimension_failures"]["outcome_verification"] == [
        "outcome_not_passed",
        "verification_not_passed",
    ]
    assert dimension_failure["dimension_failures"]["evidence_completeness"] == ["actual_outcome_evidence_missing"]
    low_score_failure = exc_info.value.failures[1]
    assert low_score_failure["overall_score"] == 0.35
    assert low_score_failure["minimum_overall_score"] == 0.75
