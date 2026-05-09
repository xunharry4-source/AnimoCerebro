from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_create_task_real(real_ci_runtime) -> None:
    """功能：验证 create_task 写入后可被 get_task 与 list_tasks 查询命中。"""
    suffix = unique_suffix()
    source_module = f"ci_create_task_{suffix}"
    payload = task_payload(suffix=suffix, title_prefix="create-task", source_module=source_module)

    created = await real_ci_runtime.task_service.create_task(payload)
    try:
        assert created.task_id
        assert created.title == payload["title"]

        queried = real_ci_runtime.task_service.get_task(created.task_id)
        assert queried is not None, "create_task 后 get_task 查询不到任务"
        assert queried.task_id == created.task_id
        assert queried.idempotency_key == payload["idempotency_key"]
        assert queried.metadata["source_module"] == source_module

        listed = real_ci_runtime.task_service.list_tasks(source_module=source_module, limit=1, offset=0)
        assert [item.task_id for item in listed] == [created.task_id], "create_task 后分页过滤查询未精确命中新增任务"
    finally:
        real_ci_runtime.task_service.bulk_delete([created.task_id], force=True)
