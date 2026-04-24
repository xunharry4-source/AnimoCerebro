from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_complete_task_with_verification_real(real_ci_runtime) -> None:
    """功能：验证 complete_task_with_verification 成功完成并可查询终态。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="verify"))
    out = await real_ci_runtime.task_service.complete_task_with_verification(task.task_id, result={"ok": True})
    assert isinstance(out, dict)
    assert out.get("success") is True
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None
    assert queried.task_id == task.task_id
    assert queried.status.value == "done"
