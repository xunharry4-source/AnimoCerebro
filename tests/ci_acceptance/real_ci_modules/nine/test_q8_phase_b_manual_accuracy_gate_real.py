from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_phase_b_manual_accuracy_gate import (
    Q8PhaseBManualAccuracyGateError,
    build_q8_phase_b_manual_accuracy_gate_report,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(session_id: str, suffix: str, count: int = 100) -> dict:
    rows = [
        {
            "task_id": f"phase-b-accuracy-{suffix}-{index:03d}",
            "title": f"phase b manual accuracy sample {suffix} #{index:03d}",
            "reason": "验证人工标注准确率样本，减少评分误差",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "manual label captured"],
            "acceptance_conditions": ["manual label is bound to task outcome"],
            "expected_outcome": {"sample_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "medium"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-accuracy-{suffix}",
            "summary": "Q8 Phase B 100-label accuracy gate test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b 100-label accuracy gate {suffix}",
                    "primary_objectives": ["verify 100 manual labels"],
                    "secondary_objectives": ["preserve scorer agreement receipts"],
                    "completion_conditions": ["100 labels are queryable"],
                    "pause_conditions": ["manual label missing"],
                    "escalation_conditions": ["accuracy below threshold"],
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


async def _complete_with_good_outcome(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {
                "task_id": task.task_id,
                "title": task.title,
                "q8_trace_id": task.metadata["trace_id"],
                "evidence": [f"manual accuracy evidence for {task.task_id}"],
            },
            "evidence": [f"manual accuracy verification receipt for {task.task_id}"],
        },
        remarks="phase b manual accuracy outcome",
    )
    assert completed["success"] is True
    outcome = task_service.get_task_outcome(task.task_id)
    assert outcome is not None
    assert outcome["overall_passed"] is True
    assert outcome["actual_outcome"]["task_id"] == task.task_id


async def _write_manual_review(
    task_service,
    task,
    suffix: str,
    index: int,
    *,
    scorer_decision: str,
    human_label: str,
) -> None:
    review = {
        "review_id": f"phase-b-accuracy-review-{suffix}-{index:03d}",
        "reviewer_id": f"phase-b-accuracy-reviewer-{suffix}",
        "reviewed_at": f"2026-04-28T17:{index // 60:02d}:{index % 60:02d}+08:00",
        "task_id": task.task_id,
        "q8_trace_id": task.metadata["trace_id"],
        "scorer_layer": "phase_b_rule_based",
        "scorer_decision": scorer_decision,
        "human_label": human_label,
        "review_evidence": [f"100-label manual accuracy review for {task.task_id}"],
    }
    await task_service.update_task_metadata(
        task.task_id,
        {"phase_b_manual_review": review},
        remarks="Phase B 100-label manual accuracy review.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_b_manual_review"] == review


async def _prepare_reviewed_tasks(real_ci_runtime, *, suffix: str, session_id: str, disagreements: int) -> list:
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 100),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 100
    tasks.sort(key=lambda task: task.title)

    for index, task in enumerate(tasks):
        await _complete_with_good_outcome(real_ci_runtime.task_service, task)
        human_label = "reject" if index < disagreements else "accept"
        await _write_manual_review(
            real_ci_runtime.task_service,
            task,
            suffix,
            index,
            scorer_decision="accept",
            human_label=human_label,
        )
    refreshed = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(refreshed) == 100
    assert all(task.metadata.get("phase_b_manual_review") for task in refreshed)
    assert all(real_ci_runtime.task_service.get_task_outcome(task.task_id) for task in refreshed)
    return refreshed


@pytest.mark.asyncio
async def test_q8_phase_b_manual_accuracy_gate_passes_with_100_real_reviewed_labels(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-accuracy-{suffix}"
    await _prepare_reviewed_tasks(
        real_ci_runtime,
        suffix=suffix,
        session_id=session_id,
        disagreements=20,
    )

    report = build_q8_phase_b_manual_accuracy_gate_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=100,
        required_label_count=100,
        minimum_accuracy=0.75,
    )

    assert report["manual_accuracy_gate_status"] == "passed"
    assert report["session_id"] == session_id
    assert report["expected_task_count"] == 100
    assert report["required_label_count"] == 100
    assert report["reviewed_count"] == 100
    assert report["agreement_count"] == 80
    assert report["disagreement_count"] == 20
    assert report["accuracy"] == 0.8
    assert report["minimum_accuracy"] == 0.75
    assert report["layer_counts"]["phase_b_rule_based"] == 100
    assert report["scorer_decision_counts"] == {"accept": 100, "downgrade": 0, "reject": 0}
    assert report["human_label_counts"] == {"accept": 80, "downgrade": 0, "reject": 20}
    assert len(report["receipts"]) == 100
    assert len(report["disagreement_receipts"]) == 20
    assert all(receipt["outcome_passed"] is True for receipt in report["receipts"])


@pytest.mark.asyncio
async def test_q8_phase_b_manual_accuracy_gate_fails_when_100_label_accuracy_is_low(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-accuracy-low-{suffix}"
    await _prepare_reviewed_tasks(
        real_ci_runtime,
        suffix=suffix,
        session_id=session_id,
        disagreements=30,
    )

    with pytest.raises(Q8PhaseBManualAccuracyGateError) as exc_info:
        build_q8_phase_b_manual_accuracy_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=100,
            required_label_count=100,
            minimum_accuracy=0.75,
        )

    assert exc_info.value.failures == [
        {
            "reason": "manual_review_agreement_below_threshold",
            "agreement_rate": 0.7,
            "minimum_agreement_rate": 0.75,
        }
    ]


@pytest.mark.asyncio
async def test_q8_phase_b_manual_accuracy_gate_fails_when_required_label_count_exceeds_scope(
    real_ci_runtime,
) -> None:
    with pytest.raises(Q8PhaseBManualAccuracyGateError) as exc_info:
        build_q8_phase_b_manual_accuracy_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id="q8-phase-b-accuracy-invalid-scope",
            expected_task_count=99,
            required_label_count=100,
            minimum_accuracy=0.75,
        )

    assert exc_info.value.failures == [
        {
            "reason": "required_label_count_exceeds_expected_task_count",
            "required_label_count": 100,
            "expected_task_count": 99,
        }
    ]
