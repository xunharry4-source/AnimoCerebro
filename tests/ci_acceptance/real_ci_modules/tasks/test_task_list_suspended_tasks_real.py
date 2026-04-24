from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_list_suspended_tasks_real(real_ci_runtime) -> None:
    """功能：验证 list_suspended_tasks 返回列表。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="listsuspended"))
    await real_ci_runtime.task_service.suspend_task(task.task_id, reason="ci")
    rows = real_ci_runtime.task_service.list_suspended_tasks()
    assert isinstance(rows, list)
    assert any(getattr(item, "task_id", "") == task.task_id for item in rows), "挂起列表中未找到目标任务"
