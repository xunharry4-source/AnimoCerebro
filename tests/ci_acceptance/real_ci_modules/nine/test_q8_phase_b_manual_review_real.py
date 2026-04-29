from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_phase_b_manual_review import (
    Q8PhaseBManualReviewError,
    build_q8_phase_b_manual_review_report,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _q9_snapshot(suffix: str) -> dict:
    evaluation_profile = {
        "role_context": "phase b manual review",
        "resource_context": "real scorer calibration",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "risk_control": 0.55,
            "continuity": 0.15,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "phase_b_manual_review",
        "action_rhythm_hint": "calibrate_after_real_score",
    }
    return {
        "trace_id": f"trace-q9-phase-b-manual-review-{suffix}",
        "summary": "Q9 Phase B manual review profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int = 4) -> dict:
    rows = [
        {
            "task_id": f"phase-b-manual-review-{suffix}-{index}",
            "title": f"phase b manual review task {suffix} #{index}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["manual review can calibrate scoring result"],
            "expected_outcome": {"review_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-manual-review-{suffix}",
            "summary": "Q8 Phase B manual review calibration test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b manual review mission {suffix}",
                    "primary_objectives": ["calibrate Q8 value scorer with human review"],
                    "secondary_objectives": ["preserve review evidence"],
                    "completion_conditions": ["manual review coverage and agreement pass"],
                    "pause_conditions": ["missing manual review"],
                    "escalation_conditions": ["low human agreement"],
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
                "evidence": [f"real manual review calibration evidence for {task.task_id}"],
            },
            "evidence": [f"real manual review calibration receipt for {task.task_id}"],
        },
        remarks="phase b manual review source outcome",
    )
    assert completed["success"] is True
    persisted = task_service.get_task_outcome(task.task_id)
    assert persisted is not None
    assert persisted["overall_passed"] is True
    assert persisted["actual_outcome"]["task_id"] == task.task_id
    assert persisted["actual_outcome"]["evidence"]


async def _write_manual_review(
    task_service,
    task,
    suffix: str,
    index: int,
    *,
    scorer_decision: str = "accept",
    human_label: str = "accept",
) -> dict:
    review = {
        "review_id": f"phase-b-manual-review-{suffix}-{index}",
        "reviewer_id": f"phase-b-reviewer-{suffix}",
        "reviewed_at": f"2026-04-28T16:{index:02d}:00+08:00",
        "task_id": task.task_id,
        "q8_trace_id": task.metadata["trace_id"],
        "scorer_layer": "phase_b_rule_based",
        "scorer_decision": scorer_decision,
        "human_label": human_label,
        "review_evidence": [f"reviewed scorer receipt and task outcome for {task.task_id}"],
    }
    await task_service.update_task_metadata(
        task.task_id,
        {"phase_b_manual_review": review},
        remarks="Phase B manual review evidence recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_b_manual_review"] == review
    return review


@pytest.mark.asyncio
async def test_q8_phase_b_manual_review_reports_real_review_coverage_and_agreement(real_ci_runtime) -> None:
    """查询链路：人工抽查校准必须读取真实任务、真实 outcome 和真实 review metadata。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-manual-review-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 4),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 4
    for task in tasks:
        await _complete_with_good_outcome(real_ci_runtime.task_service, task)
    for index, task in enumerate(tasks[:2]):
        await _write_manual_review(real_ci_runtime.task_service, task, suffix, index)

    report = build_q8_phase_b_manual_review_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=4,
        minimum_review_count=2,
        minimum_review_ratio=0.50,
        minimum_agreement_rate=1.0,
    )

    assert report["manual_review_status"] == "passed"
    assert report["session_id"] == session_id
    assert report["required_review_count"] == 2
    assert report["reviewed_count"] == 2
    assert report["agreement_count"] == 2
    assert report["disagreement_count"] == 0
    assert report["agreement_rate"] == 1.0
    assert report["layer_counts"]["phase_b_rule_based"] == 2
    assert report["human_label_counts"] == {"accept": 2, "downgrade": 0, "reject": 0}
    assert report["scorer_decision_counts"] == {"accept": 2, "downgrade": 0, "reject": 0}
    assert {receipt["task_id"] for receipt in report["receipts"]} == {task.task_id for task in tasks[:2]}
    assert all(receipt["outcome_passed"] is True for receipt in report["receipts"])
    assert all(receipt["agreement"] is True for receipt in report["receipts"])


@pytest.mark.asyncio
async def test_q8_phase_b_manual_review_fails_when_review_count_is_below_required(real_ci_runtime) -> None:
    """异常链路：抽查数量不足时必须 fail-closed，不允许把未抽查任务算作已校准。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-manual-review-low-count-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 3),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    for task in tasks:
        await _complete_with_good_outcome(real_ci_runtime.task_service, task)
    await _write_manual_review(real_ci_runtime.task_service, tasks[0], suffix, 0)

    with pytest.raises(Q8PhaseBManualReviewError) as exc_info:
        build_q8_phase_b_manual_review_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=3,
            minimum_review_count=2,
            minimum_review_ratio=0.50,
        )

    assert exc_info.value.failures == [
        {
            "reason": "manual_review_count_below_required",
            "required_review_count": 2,
            "reviewed_count": 1,
        }
    ]


@pytest.mark.asyncio
async def test_q8_phase_b_manual_review_fails_when_human_agreement_is_below_threshold(real_ci_runtime) -> None:
    """异常链路：人工标签与 scorer 决策不一致率过高时必须返回真实 disagreement。"""
    suffix = unique_suffix()
    session_id = f"q8-phase-b-manual-review-disagree-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 2),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    for task in tasks:
        await _complete_with_good_outcome(real_ci_runtime.task_service, task)
    await _write_manual_review(real_ci_runtime.task_service, tasks[0], suffix, 0)
    await _write_manual_review(
        real_ci_runtime.task_service,
        tasks[1],
        suffix,
        1,
        scorer_decision="accept",
        human_label="reject",
    )

    with pytest.raises(Q8PhaseBManualReviewError) as exc_info:
        build_q8_phase_b_manual_review_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=2,
            minimum_review_count=2,
            minimum_review_ratio=1.0,
            minimum_agreement_rate=1.0,
        )

    assert exc_info.value.failures == [
        {
            "reason": "manual_review_agreement_below_threshold",
            "agreement_rate": 0.5,
            "minimum_agreement_rate": 1.0,
        }
    ]
