from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_task_statistics_real(real_ci_runtime) -> None:
    """功能：验证 get_task_statistics 查询结果真实反映任务增删状态。"""
    suffix = unique_suffix()
    before = real_ci_runtime.task_service.get_task_statistics()
    before_total = int(before.get("total_tasks", 0))
    before_todo = int(before.get("tasks_by_status", {}).get("todo", 0))

    created = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="stats"))
    assert created.task_id

    out = real_ci_runtime.task_service.get_task_statistics()
    assert isinstance(out, dict)
    assert out["source"] == "database"
    assert out["total_tasks"] == before_total + 1
    assert out["tasks_by_status"]["todo"] == before_todo + 1
    assert out["active_tasks"] >= out["tasks_by_status"]["todo"]

    queried = real_ci_runtime.task_service.get_task(created.task_id)
    assert queried is not None
    assert queried.task_id == created.task_id
    assert queried.title == f"stats-{suffix}"
    assert queried.status.value == "todo"

    deleted = real_ci_runtime.task_service.bulk_delete([created.task_id], force=True)
    assert any(item["task_id"] == created.task_id for item in deleted["success"])
    assert real_ci_runtime.task_service.get_task(created.task_id) is None

    after_delete = real_ci_runtime.task_service.get_task_statistics()
    assert after_delete["total_tasks"] == before_total
    assert after_delete["tasks_by_status"]["todo"] == before_todo
