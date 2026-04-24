from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_task_intervene_real(real_ci_runtime) -> None:
    """功能：验证任务服务真实干预（resume）。"""
    runtime = real_ci_runtime
    suffix = uuid4().hex[:10]

    task = await runtime.task_service.create_task(
        {
            "title": f"real-ci-task-intervene-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_real_modules",
            "idempotency_key": f"task-intervene-{suffix}",
            "metadata": {"source_module": "ci_real_tasks"},
        }
    )
    before = runtime.task_service.get_task(task.task_id)
    assert before is not None and before.status.value == "todo", "干预前任务状态应为 todo"

    receipt = await runtime.task_service.intervene(
        task.task_id,
        action="resume",
        idempotency_key=f"intervene-{suffix}",
        remarks="CI 真实干预",
        operator_id="ci_real_modules",
    )
    assert receipt.get("new_status") == "in_progress", "任务干预状态错误"
    queried = runtime.task_service.get_task(task.task_id)
    assert queried is not None, "干预后查询不到任务"
    assert queried.status.value == "in_progress", "干预后查询状态与返回值不一致"
    grouped = runtime.task_service.list_tasks_grouped()
    assert any(item.task_id == task.task_id for item in grouped["in_progress"]), "干预后任务应出现在 in_progress 分组"
