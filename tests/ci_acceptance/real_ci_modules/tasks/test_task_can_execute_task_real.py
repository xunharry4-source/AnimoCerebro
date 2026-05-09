from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_can_execute_task_real(real_ci_runtime) -> None:
    """功能：验证 can_execute_task 返回可执行判定。"""
    suffix = unique_suffix()
    a = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="canexec"))
    out = real_ci_runtime.task_service.can_execute_task(a.task_id)
    assert isinstance(out, dict) and "can_execute" in out
    assert out.get("can_execute") is True
    assert out.get("dependencies_satisfied") is True
