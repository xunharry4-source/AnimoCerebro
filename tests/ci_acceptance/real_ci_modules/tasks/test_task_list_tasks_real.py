from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_list_tasks_real(real_ci_runtime) -> None:
    """功能：验证 list_tasks 查询。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="list"))
    rows = real_ci_runtime.task_service.list_tasks()
    assert any(item.task_id == task.task_id for item in rows), "list_tasks 未返回刚创建的任务"
