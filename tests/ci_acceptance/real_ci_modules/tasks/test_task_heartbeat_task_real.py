from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_heartbeat_task_real(real_ci_runtime) -> None:
    """功能：验证 heartbeat_task 心跳更新。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="hb"))
    before = real_ci_runtime.task_service.get_task(task.task_id)
    assert before is not None, "心跳前查询不到任务"
    before_ts = before.last_updated_at
    await real_ci_runtime.task_service.heartbeat_task(task.task_id)
    after = real_ci_runtime.task_service.get_task(task.task_id)
    assert after is not None, "心跳后查询不到任务"
    assert after.last_updated_at >= before_ts, "heartbeat_task 未更新 last_updated_at"
