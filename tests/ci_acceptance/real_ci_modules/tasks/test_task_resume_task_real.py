from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_resume_task_real(real_ci_runtime) -> None:
    """功能：验证 resume_task 恢复挂起。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="resume"))
    await real_ci_runtime.task_service.suspend_task(task.task_id, reason="ci")
    out = await real_ci_runtime.task_service.resume_task(task.task_id, remarks="back")
    assert out.status.value == "todo"
