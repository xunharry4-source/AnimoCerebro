from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_suspend_task_real(real_ci_runtime) -> None:
    """功能：验证 suspend_task 挂起任务。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="suspend"))
    before = real_ci_runtime.task_service.get_task(task.task_id)
    assert before is not None and before.status.value == "todo", "挂起前状态应为 todo"
    out = await real_ci_runtime.task_service.suspend_task(task.task_id, reason="ci")
    assert out.status.value == "suspended"
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None and queried.status.value == "suspended", "suspend_task 后查询状态不一致"
    suspended = real_ci_runtime.task_service.get_suspended_task(task.task_id)
    assert suspended is not None and suspended.task_id == task.task_id, "挂起后应能通过 get_suspended_task 查询到记录"
