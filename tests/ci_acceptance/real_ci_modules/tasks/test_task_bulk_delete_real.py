from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_bulk_delete_real(real_ci_runtime) -> None:
    """功能：验证 bulk_delete 批量删除。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="bulkdel"))
    out = real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)
    assert any(item.get("task_id") == task.task_id for item in out.get("success", [])), "bulk_delete 未返回目标任务成功记录"
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is None, "bulk_delete 后查询仍能读到任务"
