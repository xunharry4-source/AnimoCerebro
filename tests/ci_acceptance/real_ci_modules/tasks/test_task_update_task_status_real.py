from __future__ import annotations

import pytest

from zentex.tasks.models import TaskStatus
from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_update_task_status_real(real_ci_runtime) -> None:
    """功能：验证 update_task_status 状态流转。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="status"))
    out = await real_ci_runtime.task_service.update_task_status(task.task_id, TaskStatus.IN_PROGRESS, remarks="go")
    assert out.status.value == "in_progress"
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None, "状态更新后查询不到任务"
    assert queried.status.value == "in_progress", "状态更新后查询结果不一致"
