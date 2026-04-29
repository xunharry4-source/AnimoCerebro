from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_list_suspended_tasks_real(real_ci_runtime) -> None:
    """功能：验证 list_suspended_tasks 返回列表。"""
    suffix = unique_suffix()
    source_module = f"ci_list_suspended_{suffix}"
    task = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=suffix, title_prefix="listsuspended", source_module=source_module)
    )
    try:
        await real_ci_runtime.task_service.suspend_task(task.task_id, reason="ci")
        rows = real_ci_runtime.task_service.list_suspended_tasks(task_id=task.task_id, limit=1, offset=0)
        assert isinstance(rows, list)
        assert [getattr(item, "task_id", "") for item in rows] == [task.task_id], (
            "分页过滤挂起列表未精确命中目标任务"
        )
        queried = real_ci_runtime.task_service.get_task(task.task_id)
        assert queried is not None and queried.status.value == "suspended"
    finally:
        current = real_ci_runtime.task_service.get_task(task.task_id)
        if current is not None:
            if current.status.value == "suspended":
                await real_ci_runtime.task_service.resume_task(task.task_id, remarks="ci cleanup")
            real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)
