from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_bulk_suspend_real(real_ci_runtime) -> None:
    """功能：验证 bulk_suspend 批量挂起。"""
    suffix = unique_suffix()
    source_module = f"ci_bulk_suspend_{suffix}"
    task = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=suffix, title_prefix="bulksusp", source_module=source_module)
    )
    try:
        out = await real_ci_runtime.task_service.bulk_suspend([task.task_id], reason="ci")
        assert [item.get("task_id") for item in out.get("success", [])] == [task.task_id], (
            "bulk_suspend 未返回目标任务成功记录"
        )
        queried = real_ci_runtime.task_service.get_task(task.task_id)
        assert queried is not None and queried.status.value == "suspended", "bulk_suspend 后查询状态不一致"
        suspended_rows = real_ci_runtime.task_service.list_suspended_tasks(
            task_id=task.task_id,
            limit=1,
            offset=0,
        )
        assert [item.task_id for item in suspended_rows] == [task.task_id], (
            "bulk_suspend 后分页过滤挂起查询未精确命中目标任务"
        )
    finally:
        current = real_ci_runtime.task_service.get_task(task.task_id)
        if current is not None:
            if current.status.value == "suspended":
                await real_ci_runtime.task_service.resume_task(task.task_id, remarks="ci cleanup")
            real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)
