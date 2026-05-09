from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_dependent_tasks_real(real_ci_runtime) -> None:
    """功能：验证 get_dependent_tasks 返回列表。"""
    suffix = unique_suffix()
    source_module = f"ci_dependent_{suffix}"
    root = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}root", title_prefix="dep", source_module=source_module)
    )
    child = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}child", title_prefix="dep", source_module=source_module)
    )
    try:
        real_ci_runtime.task_service.add_dependency(child.task_id, root.task_id)
        rows = real_ci_runtime.task_service.get_dependent_tasks(root.task_id, limit=1, offset=0)
        assert isinstance(rows, list)
        assert [getattr(item, "task_id", "") for item in rows] == [child.task_id], (
            "dependent_tasks 分页过滤查询未精确返回依赖方任务"
        )
    finally:
        real_ci_runtime.task_service.bulk_delete([child.task_id, root.task_id], force=True)
