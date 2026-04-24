from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_bulk_resume_real(real_ci_runtime) -> None:
    """功能：验证 bulk_resume 批量恢复（当前实现为同步调用）。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="bulkresume"))
    await real_ci_runtime.task_service.suspend_task(task.task_id, reason="ci")
    out = real_ci_runtime.task_service.bulk_resume([task.task_id], remarks="ci")
    assert out.get("requested") == 1
    assert out.get("resumed") == 1
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None and queried.status.value in {"todo", "in_progress"}, "bulk_resume 后查询状态异常"
