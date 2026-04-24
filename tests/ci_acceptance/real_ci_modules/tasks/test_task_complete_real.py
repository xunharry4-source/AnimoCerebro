from __future__ import annotations

from uuid import uuid4

import pytest

from zentex.tasks.models import TaskStatus


@pytest.mark.asyncio
@pytest.mark.integration
async def test_task_complete_real(real_ci_runtime) -> None:
    """功能：验证任务服务真实完成任务。"""
    runtime = real_ci_runtime
    suffix = uuid4().hex[:10]

    task = await runtime.task_service.create_task(
        {
            "title": f"real-ci-task-complete-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_real_modules",
            "idempotency_key": f"task-complete-{suffix}",
            "metadata": {"source_module": "ci_real_tasks"},
        }
    )
    # 中间状态 1：创建后应为 TODO，并能通过查询接口读到。
    created = runtime.task_service.get_task(task.task_id)
    assert created is not None and created.status.value == "todo", "创建后任务状态应为 todo"
    grouped_before = runtime.task_service.list_tasks_grouped()
    assert any(item.task_id == task.task_id for item in grouped_before["pending"]), "TODO 任务应在 pending 分组"

    await runtime.task_service.intervene(
        task.task_id,
        action="resume",
        idempotency_key=f"task-complete-resume-{suffix}",
        remarks="进入执行中",
        operator_id="ci_real_modules",
    )
    # 中间状态 2：干预后应为 IN_PROGRESS，并可通过分组查询验证。
    mid = runtime.task_service.get_task(task.task_id)
    assert mid is not None and mid.status.value == "in_progress", "干预后任务状态应为 in_progress"
    grouped_mid = runtime.task_service.list_tasks_grouped()
    assert any(item.task_id == task.task_id for item in grouped_mid["in_progress"]), "in_progress 任务应在 in_progress 分组"

    updated = await runtime.task_service.update_task_status(
        task.task_id,
        TaskStatus.DONE,
        remarks="CI 真实完成",
    )
    assert updated.status.value == "done", "任务完成状态错误"
    # 最终状态：DONE 后通过查询接口与分组接口双重验证。
    final = runtime.task_service.get_task(task.task_id)
    assert final is not None and final.status.value == "done", "完成后任务状态应为 done"
    grouped_final = runtime.task_service.list_tasks_grouped()
    assert any(item.task_id == task.task_id for item in grouped_final["completed"]), "done 任务应在 completed 分组"
