from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_task_create_real(real_ci_runtime) -> None:
    """功能：验证任务服务真实创建任务。"""
    runtime = real_ci_runtime
    suffix = uuid4().hex[:10]

    task = await runtime.task_service.create_task(
        {
            "title": f"real-ci-task-create-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_real_modules",
            "idempotency_key": f"task-create-{suffix}",
            "metadata": {"source_module": "ci_real_tasks"},
        }
    )
    assert str(task.task_id).strip(), "任务创建失败"

    listed = runtime.task_service.list_tasks(source_module="ci_real_tasks")
    assert any(item.task_id == task.task_id for item in listed), "创建后任务不可见"
