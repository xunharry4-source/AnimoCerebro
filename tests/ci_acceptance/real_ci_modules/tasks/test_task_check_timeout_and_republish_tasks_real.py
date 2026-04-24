from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_task_check_timeout_and_republish_tasks_real(real_ci_runtime) -> None:
    """功能：验证 check_timeout_and_republish_tasks 返回列表。"""
    rows = await real_ci_runtime.task_service.check_timeout_and_republish_tasks(limit=10)
    assert isinstance(rows, list)
    for task in rows[:3]:
        assert getattr(task, "task_id", "")
