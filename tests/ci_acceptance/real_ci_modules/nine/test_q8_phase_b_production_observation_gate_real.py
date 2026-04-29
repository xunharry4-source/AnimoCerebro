from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_phase_b_production_observation_gate import (
    Q8PhaseBProductionObservationGateError,
    build_q8_phase_b_production_observation_gate_report,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(session_id: str, suffix: str, count: int) -> dict:
    rows = [
        {
            "task_id": f"phase-b-production-observation-{suffix}-{index:03d}",
            "title": f"phase b production observation sample {suffix} #{index:03d}",
            "reason": "验证生产历史 Q8 样本与一周误杀率观测",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "production observation captured"],
            "acceptance_conditions": ["production history sample is bound to task outcome"],
            "expected_outcome": {"sample_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "medium"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-b-production-observation-{suffix}",
            "summary": "Q8 Phase B production observation gate test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase b production observation gate {suffix}",
                    "primary_objectives": ["verify production history and false kill observation"],
                    "secondary_objectives": ["preserve task outcome and human label evidence"],
                    "completion_conditions": ["production observation gate passes"],
                    "pause_conditions": ["production evidence missing"],
                    "escalation_conditions": ["false kill rate exceeds threshold"],
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
                "evidence": [f"production observation evidence for {task.task_id}"],
            },
            "evidence": [f"production observation verification receipt for {task.task_id}"],
        },
        remarks="phase b production observation outcome",
    )
    assert completed["success"] is True
    outcome = task_service.get_task_outcome(task.task_id)
    assert outcome is not None
    assert outcome["overall_passed"] is True
    assert outcome["actual_outcome"]["task_id"] == task.task_id


async def _write_production_observation(
    task_service,
    task,
    suffix: str,
    index: int,
    *,
    decision: str,
    human_label: str,
    observed_day_index: int,
) -> None:
    review = {
        "review_id": f"phase-b-production-review-{suffix}-{index:03d}",
        "reviewer_id": f"phase-b-production-reviewer-{suffix}",
        "reviewed_at": f"2026-04-{21 + observed_day_index:02d}T09:{index % 60:02d}:00+08:00",
        "task_id": task.task_id,
        "q8_trace_id": task.metadata["trace_id"],
        "scorer_layer": "phase_b_rule_based",
        "scorer_decision": decision,
        "human_label": human_label,
        "review_evidence": [f"production human review evidence for {task.task_id}"],
    }
    production_observation = {
        "source": "production_history",
        "environment": "production",
        "sample_id": f"prod-q8-{suffix}-{index:03d}",
        "observed_at": f"2026-04-{21 + observed_day_index:02d}T10:{index % 60:02d}:00+08:00",
        "evidence": [f"production history export row for {task.task_id}"],
    }
    realtime_gate = {
        "enabled": True,
        "decision": decision,
        "overall_score": 0.9 if decision == "accept" else 0.2,
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
        remarks="Phase B production observation evidence recorded by real test.",
    )
    refreshed = task_service.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.metadata["phase_b_manual_review"] == review
    assert refreshed.metadata["phase_b_production_observation"] == production_observation
    assert refreshed.metadata["phase_b_realtime_gate"] == realtime_gate


async def _prepare_production_observed_tasks(
    real_ci_runtime,
    *,
    suffix: str,
    session_id: str,
    count: int,
    false_kill_indexes: set[int] | None = None,
    observation_days: int = 7,
) -> list:
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, count),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == count
    tasks.sort(key=lambda task: task.title)
    false_kill_indexes = false_kill_indexes or set()

    for index, task in enumerate(tasks):
        await _complete_with_good_outcome(real_ci_runtime.task_service, task)
        decision = "reject" if index % 10 == 0 else "accept"
        human_label = "accept" if index in false_kill_indexes else decision
        await _write_production_observation(
            real_ci_runtime.task_service,
            task,
            suffix,
            index,
            decision=decision,
            human_label=human_label,
            observed_day_index=index % observation_days,
        )

    refreshed = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(refreshed) == count
    assert all(task.metadata.get("phase_b_production_observation") for task in refreshed)
    assert all(task.metadata.get("phase_b_manual_review") for task in refreshed)
    assert all(real_ci_runtime.task_service.get_task_outcome(task.task_id) for task in refreshed)
    return refreshed


@pytest.mark.asyncio
async def test_q8_phase_b_production_observation_gate_passes_with_100_real_samples_over_7_days(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-production-observation-{suffix}"
    await _prepare_production_observed_tasks(
        real_ci_runtime,
        suffix=suffix,
        session_id=session_id,
        count=100,
        observation_days=7,
    )

    report = build_q8_phase_b_production_observation_gate_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=100,
        minimum_production_history_count=100,
        minimum_manual_label_count=100,
        minimum_observation_days=7,
        maximum_false_kill_rate=0.05,
    )

    assert report["production_observation_gate_status"] == "passed"
    assert report["session_id"] == session_id
    assert report["production_history_count"] == 100
    assert report["manual_label_count"] == 100
    assert report["observation_day_count"] == 7
    assert report["decision_counts"] == {"accept": 90, "downgrade": 0, "reject": 10}
    assert report["human_label_counts"] == {"accept": 90, "downgrade": 0, "reject": 10}
    assert report["rejected_count"] == 10
    assert report["false_kill_count"] == 0
    assert report["false_kill_rate"] == 0.0
    assert len(report["receipts"]) == 100
    assert all(receipt["outcome_passed"] is True for receipt in report["receipts"])
    assert all(receipt["production_evidence"] for receipt in report["receipts"])


@pytest.mark.asyncio
async def test_q8_phase_b_production_observation_gate_fails_when_false_kill_rate_is_high(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-production-observation-false-kill-{suffix}"
    await _prepare_production_observed_tasks(
        real_ci_runtime,
        suffix=suffix,
        session_id=session_id,
        count=20,
        false_kill_indexes={0, 10},
        observation_days=7,
    )

    with pytest.raises(Q8PhaseBProductionObservationGateError) as exc_info:
        build_q8_phase_b_production_observation_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=20,
            minimum_production_history_count=20,
            minimum_manual_label_count=20,
            minimum_observation_days=7,
            maximum_false_kill_rate=0.05,
        )

    assert exc_info.value.failures == [
        {
            "reason": "production_false_kill_rate_above_threshold",
            "false_kill_rate": 1.0,
            "maximum_false_kill_rate": 0.05,
            "false_kill_count": 2,
            "rejected_count": 2,
        }
    ]


@pytest.mark.asyncio
async def test_q8_phase_b_production_observation_gate_fails_when_observation_window_is_short(
    real_ci_runtime,
) -> None:
    suffix = unique_suffix()
    session_id = f"q8-phase-b-production-observation-short-{suffix}"
    await _prepare_production_observed_tasks(
        real_ci_runtime,
        suffix=suffix,
        session_id=session_id,
        count=10,
        observation_days=1,
    )

    with pytest.raises(Q8PhaseBProductionObservationGateError) as exc_info:
        build_q8_phase_b_production_observation_gate_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=10,
            minimum_production_history_count=10,
            minimum_manual_label_count=10,
            minimum_observation_days=7,
            maximum_false_kill_rate=0.05,
        )

    assert exc_info.value.failures == [
        {
            "reason": "production_observation_days_below_required",
            "required": 7,
            "actual": 1,
        }
    ]
