from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_dependent_tasks_real(real_ci_runtime) -> None:
    """功能：验证 get_dependent_tasks 返回列表。"""
    suffix = unique_suffix()
    root = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}root", title_prefix="dep"))
    child = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}child", title_prefix="dep"))
    real_ci_runtime.task_service.add_dependency(child.task_id, root.task_id)
    rows = real_ci_runtime.task_service.get_dependent_tasks(root.task_id)
    assert isinstance(rows, list)
    assert any(getattr(item, "task_id", "") == child.task_id for item in rows), "dependent_tasks 未返回依赖方任务"
