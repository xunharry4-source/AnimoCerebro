from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(suffix: str, task_title: str) -> dict:
    return {
        "q8": {
            "trace_id": f"trace-outcome-learning-{suffix}",
            "summary": "Q8 outcome learning writeback real test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"learn from task outcome {suffix}",
                    "primary_objectives": ["write task outcome to learning"],
                    "secondary_objectives": ["preserve verification evidence"],
                    "completion_conditions": ["learning overall record can be queried"],
                    "pause_conditions": ["task outcome missing"],
                    "escalation_conditions": ["learning writeback failed"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"q8-learning-task-{suffix}",
                            "title": task_title,
                            "priority": "high",
                            "expected_outcome": {"learning": "written"},
                            "success_criteria": ["task outcome exists", "learning record exists"],
                            "acceptance_conditions": ["task_outcomes.written_back_to_learning is true"],
                            "verification_method": "rule_based_outcome_contract",
                            "risk_assessment": {"risk_level": "medium"},
                        }
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        }
    }


@pytest.mark.asyncio
async def test_task_outcome_learning_writeback_creates_queryable_learning_real(real_ci_runtime) -> None:
    """新增/修改链路：task_outcomes 写回 Learning 后，必须能查询到 learning 与回写标记。"""
    suffix = unique_suffix()
    session_id = f"outcome-learning-{suffix}"
    task_title = f"write q8 outcome learning {suffix}"

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(suffix, task_title),
    )
    tasks = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_id, "queue_name": "next_self_tasks"},
        limit=1,
        offset=0,
    )
    assert len(tasks) == 1
    task = tasks[0]
    completed = await real_ci_runtime.task_service.complete_task_with_verification(
        task.task_id,
        result={"actual_outcome": {"learning": "written"}, "evidence": ["real learning writeback receipt"]},
        remarks="learning writeback source outcome",
    )
    assert completed["success"] is True
    before = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert before is not None
    assert before["overall_passed"] is True
    assert before["written_back_to_learning"] is False
    assert before.get("learning_trace_id") in (None, "")

    writeback = real_ci_runtime.task_service.write_task_outcome_to_learning(
        real_ci_runtime.learning_service,
        task.task_id,
    )

    assert writeback["created"] is True
    learning_trace_id = writeback["learning_trace_id"]
    after = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert after is not None
    assert after["written_back_to_learning"] is True
    assert after["learning_trace_id"] == learning_trace_id

    overall_rows = real_ci_runtime.learning_service.query_overall_records(
        limit=20,
        trace_id=learning_trace_id,
    )
    matching_overall = [item for item in overall_rows if item.detail.get("task_id") == task.task_id]
    assert len(matching_overall) == 1, "按 learning trace 查询 overall record 必须命中唯一写回记录"
    overall = matching_overall[0]
    assert overall.status == "completed"
    assert overall.direction == "nine_question_integration"
    assert overall.detail["source"] == "task_outcome_writeback"
    assert overall.detail["task_title"] == task_title
    assert overall.detail["actual_outcome"] == {"learning": "written"}
    assert overall.detail["success_criteria"] == ["task outcome exists", "learning record exists"]
    assert overall.detail["verification_result"]["overall_passed"] is True

    history_rows = real_ci_runtime.learning_service.query_history_entries(limit=200)
    matching_history = [
        item
        for item in history_rows
        if item.trace_id == learning_trace_id and item.payload.get("detail", {}).get("task_id") == task.task_id
    ]
    assert len(matching_history) == 1, "learning history 必须能查询到同一 task outcome 写回事件"

    second = real_ci_runtime.task_service.write_task_outcome_to_learning(
        real_ci_runtime.learning_service,
        task.task_id,
    )
    assert second["created"] is False
    assert second["learning_trace_id"] == learning_trace_id
    overall_again = real_ci_runtime.learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matching_again = [item for item in overall_again if item.detail.get("task_id") == task.task_id]
    assert len(matching_again) == 1, "重复写回不得创建重复 learning overall record"


def test_task_outcome_learning_writeback_requires_existing_outcome_real(real_ci_runtime) -> None:
    """异常链路：没有真实 task_outcomes 时必须 fail-closed，不能创建空 learning。"""
    suffix = unique_suffix()
    missing_task_id = f"missing-learning-outcome-{suffix}"

    with pytest.raises(Exception, match="Task outcome not found"):
        real_ci_runtime.task_service.write_task_outcome_to_learning(
            real_ci_runtime.learning_service,
            missing_task_id,
        )

    rows = real_ci_runtime.learning_service.query_history_entries(limit=200)
    assert all(
        item.payload.get("detail", {}).get("task_id") != missing_task_id
        for item in rows
    ), "缺 outcome 的失败路径不得写入 learning 假记录"
