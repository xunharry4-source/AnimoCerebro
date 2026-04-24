from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_suspended_task_real(real_ci_runtime) -> None:
    """功能：验证 get_suspended_task 查询挂起信息。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="getsusp"))
    await real_ci_runtime.task_service.suspend_task(task.task_id, reason="ci")
    s = real_ci_runtime.task_service.get_suspended_task(task.task_id)
    assert s is not None
    assert s.task_id == task.task_id
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None and queried.status.value == "suspended", "挂起后主任务查询状态不一致"
