from __future__ import annotations

import pytest

from zentex.tasks.models import TaskStatus
from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_bulk_update_status_real(real_ci_runtime) -> None:
    """功能：验证 bulk_update_status 批量更新状态。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="bulkst"))
    out = await real_ci_runtime.task_service.bulk_update_status([task.task_id], TaskStatus.IN_PROGRESS, remarks="ci")
    assert any(item.get("task_id") == task.task_id for item in out.get("success", [])), "bulk_update_status 未返回目标任务成功记录"
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None and queried.status.value == "in_progress", "bulk_update_status 后查询状态不一致"
