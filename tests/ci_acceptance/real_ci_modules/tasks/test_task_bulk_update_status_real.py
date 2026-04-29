from __future__ import annotations

import pytest

from zentex.tasks.models import TaskStatus
from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_bulk_update_status_real(real_ci_runtime) -> None:
    """功能：验证 bulk_update_status 批量更新状态。"""
    suffix = unique_suffix()
    source_module = f"ci_bulk_status_{suffix}"
    task = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=suffix, title_prefix="bulkst", source_module=source_module)
    )
    try:
        out = await real_ci_runtime.task_service.bulk_update_status([task.task_id], TaskStatus.IN_PROGRESS, remarks="ci")
        assert [item.get("task_id") for item in out.get("success", [])] == [task.task_id], (
            "bulk_update_status 未返回目标任务成功记录"
        )
        queried = real_ci_runtime.task_service.get_task(task.task_id)
        assert queried is not None and queried.status.value == "in_progress", "bulk_update_status 后查询状态不一致"
        listed = real_ci_runtime.task_service.list_tasks(
            source_module=source_module,
            status=TaskStatus.IN_PROGRESS,
            limit=1,
            offset=0,
        )
        assert [item.task_id for item in listed] == [task.task_id], "bulk_update_status 后状态过滤查询未精确命中目标任务"
    finally:
        real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)
