from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service
from zentex.reflection.experience_candidate import (
    ExperienceCandidatePromotionError,
    build_experience_candidates_from_task_outcomes,
    promote_experience_candidates_to_learning,
)


def _snapshot(session_id: str, suffix: str) -> dict:
    rows = [
        {
            "task_id": f"phase-c-experience-success-{suffix}",
            "title": f"phase c experience candidate success {suffix}",
            "reason": "验证成功 outcome 可升格为 ExperienceCandidate",
            "priority": "high",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["experience candidate can be promoted"],
            "expected_outcome": {"candidate": "success", "session_id": session_id},
            "risk_assessment": {"risk_level": "medium"},
        },
        {
            "task_id": f"phase-c-experience-failure-{suffix}",
            "title": f"phase c experience candidate failure {suffix}",
            "reason": "验证失败 outcome 可升格为 ExperienceCandidate",
            "priority": "high",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["experience candidate preserves failure verifier"],
            "expected_outcome": {"candidate": "failure", "session_id": session_id},
            "risk_assessment": {"risk_level": "medium"},
        },
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-phase-c-experience-candidate-{suffix}",
            "summary": "Q8 Phase C ExperienceCandidate promotion test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"phase c experience candidate promotion {suffix}",
                    "primary_objectives": ["promote task outcomes to experience candidates"],
                    "secondary_objectives": ["preserve reflection memory learning writeback ids"],
                    "completion_conditions": ["experience candidates are queryable in learning"],
                    "pause_conditions": ["task outcome missing"],
                    "escalation_conditions": ["candidate promotion failed"],
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


async def _complete_success(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {"candidate": "success", "task_id": task.task_id},
            "evidence": [f"success evidence for {task.task_id}"],
        },
        remarks="phase c success source outcome",
    )
    assert completed["success"] is True
    outcome = task_service.get_task_outcome(task.task_id)
    assert outcome is not None
    assert outcome["overall_passed"] is True


async def _complete_failure(task_service, task) -> None:
    completed = await task_service.complete_task_with_verification(
        task.task_id,
        result={"actual_outcome": {"candidate": "failure", "task_id": task.task_id}},
        remarks="phase c failure source outcome",
    )
    assert completed["success"] is False
    outcome = task_service.get_task_outcome(task.task_id)
    assert outcome is not None
    assert outcome["overall_passed"] is False
    verifier_results = outcome["verification_result"]["verifier_results"]
    assert verifier_results[0]["passed"] is False
    rule_results = verifier_results[0]["details"]["rule_results"]
    assert any(
        rule.get("passed") is False and "evidence" in str(rule)
        for rule in rule_results
    )


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
    assert queried["written_back_to_reflection"] is True
    assert queried["reflection_id"] == reflection["reflection_id"]
    assert queried["written_back_to_memory"] is True
    assert queried["memory_id"] == memory["memory_id"]
    assert queried["written_back_to_learning"] is True
    assert queried["learning_trace_id"] == learning["learning_trace_id"]


@pytest.mark.asyncio
async def test_phase_c_experience_candidates_promote_real_task_outcomes_to_learning(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"phase-c-experience-candidate-{suffix}"
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

    candidate_report = build_experience_candidates_from_task_outcomes(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=2,
    )
    assert candidate_report["experience_candidate_status"] == "ready"
    assert candidate_report["candidate_count"] == 2
    assert candidate_report["candidate_type_counts"] == {"success_pattern": 1, "failure_pattern": 1}
    by_task = {candidate["task_id"]: candidate for candidate in candidate_report["candidates"]}
    assert by_task[failure_task.task_id]["candidate_type"] == "failure_pattern"
    assert by_task[failure_task.task_id]["failed_verifiers"] == ["q8_required_outcome_evidence"]
    assert by_task[success_task.task_id]["candidate_type"] == "success_pattern"
    assert by_task[success_task.task_id]["reflection_id"]
    assert by_task[success_task.task_id]["memory_id"]
    assert by_task[success_task.task_id]["learning_trace_id"]

    promotion = promote_experience_candidates_to_learning(
        task_service=real_ci_runtime.task_service,
        learning_service=real_ci_runtime.learning_service,
        session_id=session_id,
        expected_task_count=2,
    )

    assert promotion["experience_candidate_promotion_status"] == "promoted"
    assert promotion["promoted_count"] == 2
    assert promotion["candidate_type_counts"] == {"success_pattern": 1, "failure_pattern": 1}
    for receipt in promotion["promotions"]:
        rows = real_ci_runtime.learning_service.query_overall_records(
            limit=20,
            trace_id=receipt["learning_trace_id"],
        )
        matching = [
            row
            for row in rows
            if row.detail.get("candidate_id") == receipt["candidate_id"]
            and row.detail.get("task_id") == receipt["task_id"]
        ]
        assert len(matching) == 1
        assert matching[0].detail["source"] == "phase_c_experience_candidate_promotion"
        assert matching[0].detail["candidate"]["candidate_type"] == receipt["candidate_type"]


@pytest.mark.asyncio
async def test_phase_c_experience_candidate_fails_when_outcome_writebacks_are_missing(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"phase-c-experience-candidate-missing-writeback-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix),
    )
    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == 2
    await _complete_success(real_ci_runtime.task_service, tasks[0])

    with pytest.raises(ExperienceCandidatePromotionError) as exc_info:
        build_experience_candidates_from_task_outcomes(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=2,
        )

    reasons = [failure["reason"] for failure in exc_info.value.failures]
    assert "reflection_writeback_missing" in reasons
    assert "memory_writeback_missing" in reasons
    assert "learning_writeback_missing" in reasons
    assert "task_outcome_missing" in reasons
