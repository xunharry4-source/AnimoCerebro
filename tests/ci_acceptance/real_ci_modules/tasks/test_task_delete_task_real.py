from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_delete_task_real(real_ci_runtime) -> None:
    """功能：验证 delete_task 删除单任务。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="delone"))
    assert real_ci_runtime.task_service.delete_task(task.task_id, force=True) is True
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is None, "delete_task 后查询仍能读到任务"
