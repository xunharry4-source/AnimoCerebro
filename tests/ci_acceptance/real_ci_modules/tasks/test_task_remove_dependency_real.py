from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_remove_dependency_real(real_ci_runtime) -> None:
    """功能：验证 remove_dependency 移除依赖。"""
    suffix = unique_suffix()
    a = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}a", title_prefix="rmdep"))
    b = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}b", title_prefix="rmdep"))
    real_ci_runtime.task_service.add_dependency(a.task_id, b.task_id)
    out = real_ci_runtime.task_service.remove_dependency(a.task_id, b.task_id)
    assert b.task_id not in out.depends_on
