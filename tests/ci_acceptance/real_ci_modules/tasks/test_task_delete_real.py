from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_task_delete_real(real_ci_runtime) -> None:
    """功能：验证任务服务真实删除任务。"""
    runtime = real_ci_runtime
    suffix = uuid4().hex[:10]

    task = await runtime.task_service.create_task(
        {
            "title": f"real-ci-task-delete-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_real_modules",
            "idempotency_key": f"task-delete-{suffix}",
            "metadata": {"source_module": "ci_real_tasks"},
        }
    )

    result = runtime.task_service.bulk_delete([task.task_id], force=True)
    assert any(item.get("task_id") == task.task_id for item in result.get("success", [])), "任务删除失败"
    assert runtime.task_service.get_task(task.task_id) is None, "删除后任务仍存在"
