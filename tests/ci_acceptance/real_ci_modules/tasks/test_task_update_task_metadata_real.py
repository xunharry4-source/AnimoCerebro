from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_update_task_metadata_real(real_ci_runtime) -> None:
    """功能：验证 update_task_metadata 更新元数据。"""
    suffix = unique_suffix()
    source_module = f"ci_meta_{suffix}"
    metadata_key = "ci_marker"
    metadata_value = f"v_{suffix}"
    task = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=suffix, title_prefix="meta", source_module=source_module)
    )
    try:
        listed_before = real_ci_runtime.task_service.list_tasks(source_module=source_module, limit=1, offset=0)
        assert [item.task_id for item in listed_before] == [task.task_id], "更新前分页过滤查询未精确命中目标任务"
        updated = await real_ci_runtime.task_service.update_task_metadata(
            task.task_id,
            {metadata_key: metadata_value},
            remarks="ok",
        )
        assert updated.metadata.get(metadata_key) == metadata_value
        queried = real_ci_runtime.task_service.get_task(task.task_id)
        assert queried is not None, "更新后查询不到任务"
        assert queried.metadata.get(metadata_key) == metadata_value, "更新后查询结果 metadata 不一致"
        listed_after = real_ci_runtime.task_service.list_tasks(
            metadata_filters={metadata_key: metadata_value},
            limit=1,
            offset=0,
        )
        assert [item.task_id for item in listed_after] == [task.task_id], "更新后 metadata 分页过滤查询未精确命中目标任务"
    finally:
        real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)
