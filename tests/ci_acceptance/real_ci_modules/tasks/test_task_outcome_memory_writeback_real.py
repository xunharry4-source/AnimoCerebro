from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(suffix: str, task_title: str) -> dict:
    return {
        "q8": {
            "trace_id": f"trace-outcome-memory-{suffix}",
            "summary": "Q8 outcome memory writeback real test",
            "context_updates": {
                "q8_objective_profile": {
                    "current_mission": f"remember task outcome {suffix}",
                    "primary_objectives": ["write task outcome to memory"],
                    "secondary_objectives": ["preserve verification evidence"],
                    "completion_conditions": ["memory record can be queried"],
                    "pause_conditions": ["task outcome missing"],
                    "escalation_conditions": ["memory writeback failed"],
                },
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"q8-memory-task-{suffix}",
                            "title": task_title,
                            "priority": "high",
                            "expected_outcome": {"memory": "written"},
                            "success_criteria": ["task outcome exists", "memory record exists"],
                            "acceptance_conditions": ["task_outcomes.written_back_to_memory is true"],
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
async def test_task_outcome_memory_writeback_creates_queryable_memory_real(real_ci_runtime) -> None:
    """新增/修改链路：task_outcomes 写回 Memory 后，必须能查询到 memory 与回写标记。"""
    suffix = unique_suffix()
    session_id = f"outcome-memory-{suffix}"
    task_title = f"write q8 outcome memory {suffix}"
    trace_id = f"trace-outcome-memory-{suffix}"

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
        result={"actual_outcome": {"memory": "written"}, "evidence": ["real memory writeback receipt"]},
        remarks="memory writeback source outcome",
    )
    assert completed["success"] is True
    before = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert before is not None
    assert before["overall_passed"] is True
    assert before["written_back_to_memory"] is False
    assert before.get("memory_id") in (None, "")

    writeback = real_ci_runtime.task_service.write_task_outcome_to_memory(
        real_ci_runtime.memory_service,
        task.task_id,
    )

    assert writeback["created"] is True
    memory_id = writeback["memory_id"]
    after = real_ci_runtime.task_service.get_task_outcome(task.task_id)
    assert after is not None
    assert after["written_back_to_memory"] is True
    assert after["memory_id"] == memory_id

    memory = real_ci_runtime.memory_service.get_record(memory_id)
    assert memory is not None
    assert memory.memory_id == memory_id
    assert memory.memory_layer == "procedural"
    assert memory.source_kind == "task_outcome_writeback"
    assert memory.trace_id == trace_id
    assert memory.target_id == task.task_id
    assert "task_outcome" in memory.tags
    assert memory.payload["task_id"] == task.task_id
    assert memory.payload["question_id"] == "q8"
    assert memory.payload["actual_outcome"] == {"memory": "written"}
    assert memory.payload["success_criteria"] == ["task outcome exists", "memory record exists"]
    assert memory.payload["verification_result"]["overall_passed"] is True

    managed_rows = real_ci_runtime.memory_service.query_managed_records(limit=200, trace_id=trace_id)
    matching_rows = [item for item in managed_rows if item.memory_id == memory_id]
    assert len(matching_rows) == 1, "按 trace_id 查询 managed memory 必须命中唯一写回记录"

    hits = real_ci_runtime.memory_service.recall(suffix, limit=50, trace_id=trace_id, target_id=task.task_id)
    assert any(getattr(hit, "memory_id", "") == memory_id for hit in hits), "recall 必须命中真实写回记忆"

    second = real_ci_runtime.task_service.write_task_outcome_to_memory(
        real_ci_runtime.memory_service,
        task.task_id,
    )
    assert second["created"] is False
    assert second["memory_id"] == memory_id
    managed_again = real_ci_runtime.memory_service.query_managed_records(limit=200, trace_id=trace_id)
    matching_again = [item for item in managed_again if item.target_id == task.task_id]
    assert len(matching_again) == 1, "重复写回不得创建重复 memory"


def test_task_outcome_memory_writeback_requires_existing_outcome_real(real_ci_runtime) -> None:
    """异常链路：没有真实 task_outcomes 时必须 fail-closed，不能创建空 memory。"""
    suffix = unique_suffix()
    missing_task_id = f"missing-memory-outcome-{suffix}"
    trace_id = f"trace-missing-memory-outcome-{suffix}"

    before = real_ci_runtime.memory_service.query_managed_records(limit=200, trace_id=trace_id)
    assert before == []

    with pytest.raises(Exception, match="Task outcome not found"):
        real_ci_runtime.task_service.write_task_outcome_to_memory(
            real_ci_runtime.memory_service,
            missing_task_id,
        )

    after = real_ci_runtime.memory_service.query_managed_records(limit=200, trace_id=trace_id)
    assert after == [], "缺 outcome 的失败路径不得写入 memory 假记录"
