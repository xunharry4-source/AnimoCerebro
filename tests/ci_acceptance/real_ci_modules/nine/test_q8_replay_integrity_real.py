from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_replay_integrity import (
    Q8ReplayIntegrityError,
    build_q8_replay_integrity_report,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _q9_snapshot(suffix: str) -> dict:
    evaluation_profile = {
        "role_context": "replay verifier",
        "resource_context": "real task replay integrity test",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.3,
            "risk_control": 0.45,
            "continuity": 0.2,
            "speed": 0.05,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "trace_integrity_first",
        "action_rhythm_hint": "verify_every_replay_step",
    }
    return {
        "trace_id": f"trace-q9-replay-{suffix}",
        "summary": "Q9 replay integrity profile",
        "context_updates": {
            "q9_evaluation_profile": evaluation_profile,
            "q9_action_posture": {"evaluation_profile": evaluation_profile},
        },
        "result": {"evaluation_profile": evaluation_profile},
    }


def _snapshot(session_id: str, suffix: str, count: int) -> dict:
    rows = [
        {
            "task_id": f"q8-replay-task-{suffix}-{index:03d}",
            "title": f"q8 replay integrity task {suffix} #{index:03d}",
            "priority": "medium",
            "success_criteria": ["actual outcome captured", "evidence captured"],
            "acceptance_conditions": ["task_outcome trace matches q8 trace"],
            "expected_outcome": {"replay_index": index, "session_id": session_id},
            "risk_assessment": {"risk_level": "high"},
        }
        for index in range(count)
    ]
    return {
        "q8": {
            "trace_id": f"trace-q8-replay-{suffix}",
            "summary": "Q8 replay integrity test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"replay integrity mission {suffix}",
                    "primary_objectives": ["verify 100 replay tasks"],
                    "secondary_objectives": ["preserve trace chain"],
                    "completion_conditions": ["all task outcomes passed"],
                    "pause_conditions": ["missing task outcome"],
                    "escalation_conditions": ["trace chain broken"],
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


@pytest.mark.asyncio
async def test_q8_replay_integrity_checks_100_real_tasks_and_outcomes(real_ci_runtime) -> None:
    """100 条回放查询链路：同步、完成、查询任务与 outcome，检查 trace 链不断。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-{suffix}"
    expected_count = 100

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, expected_count),
    )

    tasks = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})
    assert len(tasks) == expected_count
    assert all(task.priority.value == "high" for task in tasks)
    assert all(task.metadata["phase_a_evaluation"]["status"] == "ready" for task in tasks)

    for task in tasks:
        completed = await real_ci_runtime.task_service.complete_task_with_verification(
            task.task_id,
            result={
                "actual_outcome": {
                    "task_id": task.task_id,
                    "title": task.title,
                    "q8_trace_id": task.metadata["trace_id"],
                },
                "evidence": [f"real replay receipt for {task.task_id}"],
            },
            remarks="100 replay integrity receipt",
        )
        assert completed["success"] is True
        assert completed["verification_result"]["overall_passed"] is True
        outcome = real_ci_runtime.task_service.get_task_outcome(task.task_id)
        assert outcome is not None
        assert outcome["trace_id"] == task.metadata["trace_id"]
        assert outcome["overall_passed"] is True
        assert outcome["actual_outcome"]["task_id"] == task.task_id

    report = build_q8_replay_integrity_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=expected_count,
    )
    assert report["integrity_status"] == "passed"
    assert report["session_id"] == session_id
    assert report["checked_task_count"] == expected_count
    assert report["checked_outcome_count"] == expected_count
    assert report["unique_q8_trace_count"] == 1
    assert len(report["receipts"]) == expected_count
    first = report["receipts"][0]
    assert first["q8_trace_id"] == f"trace-q8-replay-{suffix}"
    assert first["q9_trace_id"] == f"trace-q9-replay-{suffix}"
    assert first["priority"] == "high"
    assert first["outcome_passed"] is True
    assert report["require_writebacks"] is False
    assert report["writeback_counts"] == {"reflection": 0, "memory": 0, "learning": 0}
    assert first["writebacks"] == {
        "reflection": {"written": False, "id": None, "verified": False},
        "memory": {"written": False, "id": None, "verified": False},
        "learning": {"written": False, "trace_id": None, "verified": False},
    }


@pytest.mark.asyncio
async def test_q8_replay_integrity_checks_required_real_writebacks(real_ci_runtime) -> None:
    """新增/查询链路：要求写回时，必须真实写入 Reflection/Memory/Learning 后报告才通过。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-writebacks-{suffix}"

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
                "writeback_required": True,
            },
            "evidence": [f"real replay writeback receipt for {task.task_id}"],
        },
        remarks="replay integrity writeback receipt",
    )
    assert completed["success"] is True

    before = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert before["written_back_to_reflection"] is False
    assert before["written_back_to_memory"] is False
    assert before["written_back_to_learning"] is False

    reflection = real_ci_runtime.task_service.write_task_outcome_to_reflection(
        real_ci_runtime.reflection_service,
        task.task_id,
    )
    memory = real_ci_runtime.task_service.write_task_outcome_to_memory(
        real_ci_runtime.memory_service,
        task.task_id,
    )
    learning = real_ci_runtime.task_service.write_task_outcome_to_learning(
        real_ci_runtime.learning_service,
        task.task_id,
    )

    after = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert after["reflection_id"] == reflection["reflection_id"]
    assert after["memory_id"] == memory["memory_id"]
    assert after["learning_trace_id"] == learning["learning_trace_id"]

    report = build_q8_replay_integrity_report(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        expected_task_count=1,
        require_writebacks=True,
        reflection_service=real_ci_runtime.reflection_service,
        memory_service=real_ci_runtime.memory_service,
        learning_service=real_ci_runtime.learning_service,
    )
    assert report["integrity_status"] == "passed"
    assert report["require_writebacks"] is True
    assert report["writeback_counts"] == {"reflection": 1, "memory": 1, "learning": 1}
    assert report["receipts"][0]["writebacks"] == {
        "reflection": {"written": True, "id": reflection["reflection_id"], "verified": True},
        "memory": {"written": True, "id": memory["memory_id"], "verified": True},
        "learning": {"written": True, "trace_id": learning["learning_trace_id"], "verified": True},
    }


@pytest.mark.asyncio
async def test_q8_replay_integrity_fails_when_outcome_is_missing(real_ci_runtime) -> None:
    """异常链路：查询完整性时如果 task_outcomes 缺失，必须抛错，不能返回假通过。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-missing-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )

    with pytest.raises(Q8ReplayIntegrityError) as exc_info:
        build_q8_replay_integrity_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=1,
        )

    assert exc_info.value.failures == [
        {
            "reason": "task_outcome_missing",
            "task_id": real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0].task_id,
        }
    ]


@pytest.mark.asyncio
async def test_q8_replay_integrity_fails_when_required_writebacks_are_missing(real_ci_runtime) -> None:
    """异常链路：要求写回但 outcome 未写回时，必须精确列出缺失写回项。"""
    suffix = unique_suffix()
    session_id = f"q8-replay-missing-writebacks-{suffix}"
    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix, 1),
    )
    task = real_ci_runtime.task_service.list_tasks(metadata_filters={"session_id": session_id})[0]
    completed = await real_ci_runtime.task_service.complete_task_with_verification(
        task.task_id,
        result={
            "actual_outcome": {"task_id": task.task_id, "q8_trace_id": task.metadata["trace_id"]},
            "evidence": [f"real missing writeback receipt for {task.task_id}"],
        },
        remarks="missing writeback source outcome",
    )
    assert completed["success"] is True

    with pytest.raises(Q8ReplayIntegrityError) as exc_info:
        build_q8_replay_integrity_report(
            task_service=real_ci_runtime.task_service,
            session_id=session_id,
            expected_task_count=1,
            require_writebacks=True,
            reflection_service=real_ci_runtime.reflection_service,
            memory_service=real_ci_runtime.memory_service,
            learning_service=real_ci_runtime.learning_service,
        )

    assert exc_info.value.failures == [
        {"reason": "reflection_writeback_missing", "task_id": task.task_id},
        {"reason": "memory_writeback_missing", "task_id": task.task_id},
        {"reason": "learning_writeback_missing", "task_id": task.task_id},
    ]
