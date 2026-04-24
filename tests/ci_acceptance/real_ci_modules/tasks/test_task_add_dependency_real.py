from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_add_dependency_real(real_ci_runtime) -> None:
    """功能：验证 add_dependency 添加依赖。"""
    suffix = unique_suffix()
    a = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}a", title_prefix="dep"))
    b = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}b", title_prefix="dep"))
    out = real_ci_runtime.task_service.add_dependency(a.task_id, b.task_id)
    assert b.task_id in out.depends_on
