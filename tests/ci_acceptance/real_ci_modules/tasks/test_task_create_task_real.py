from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_create_task_real(real_ci_runtime) -> None:
    """功能：验证 create_task 写入后可被 get_task 与 list_tasks 查询命中。"""
    suffix = unique_suffix()
    payload = task_payload(suffix=suffix, title_prefix="create-task")

    created = await real_ci_runtime.task_service.create_task(payload)
    assert created.task_id
    assert created.title == payload["title"]

    queried = real_ci_runtime.task_service.get_task(created.task_id)
    assert queried is not None, "create_task 后 get_task 查询不到任务"
    assert queried.task_id == created.task_id
    assert queried.idempotency_key == payload["idempotency_key"]

    listed = real_ci_runtime.task_service.list_tasks(source_module="ci_real_tasks")
    assert any(item.task_id == created.task_id for item in listed), "create_task 后 list_tasks 未命中新增任务"
