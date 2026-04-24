from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_update_task_metadata_real(real_ci_runtime) -> None:
    """功能：验证 update_task_metadata 更新元数据。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="meta"))
    listed_before = real_ci_runtime.task_service.list_tasks(source_module="ci_real_tasks")
    assert any(item.task_id == task.task_id for item in listed_before), "更新前 list_tasks 未包含目标任务"
    updated = await real_ci_runtime.task_service.update_task_metadata(task.task_id, {"k": "v"}, remarks="ok")
    assert updated.metadata.get("k") == "v"
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None, "更新后查询不到任务"
    assert queried.metadata.get("k") == "v", "更新后查询结果 metadata 不一致"
    listed_after = real_ci_runtime.task_service.list_tasks(metadata_filters={"k": "v"})
    assert any(item.task_id == task.task_id for item in listed_after), "更新后 metadata 过滤查询未命中目标任务"
