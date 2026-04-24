from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_bulk_suspend_real(real_ci_runtime) -> None:
    """功能：验证 bulk_suspend 批量挂起。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="bulksusp"))
    out = await real_ci_runtime.task_service.bulk_suspend([task.task_id], reason="ci")
    assert any(item.get("task_id") == task.task_id for item in out.get("success", [])), "bulk_suspend 未返回目标任务成功记录"
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None and queried.status.value == "suspended", "bulk_suspend 后查询状态不一致"
    suspended_rows = real_ci_runtime.task_service.list_suspended_tasks()
    assert any(item.task_id == task.task_id for item in suspended_rows), "bulk_suspend 后 list_suspended_tasks 未包含目标任务"
