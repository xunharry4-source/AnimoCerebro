from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_list_tasks_grouped_real(real_ci_runtime) -> None:
    """功能：验证 list_tasks_grouped 分组。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="group"))
    grouped = real_ci_runtime.task_service.list_tasks_grouped()
    assert set(grouped.keys()) == {"in_progress", "pending", "waiting_confirmation", "completed", "cancelled"}
    assert any(item.task_id == task.task_id for item in grouped["pending"]), "新建 TODO 任务应出现在 pending 分组"
