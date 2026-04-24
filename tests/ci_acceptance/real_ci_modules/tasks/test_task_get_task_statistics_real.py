from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_task_statistics_real(real_ci_runtime) -> None:
    """功能：验证 get_task_statistics 返回统计结构。"""
    suffix = unique_suffix()
    created = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="stats"))
    assert created.task_id
    out = real_ci_runtime.task_service.get_task_statistics()
    assert isinstance(out, dict)
    assert out.get("total_tasks", 0) >= 1
    assert isinstance(out.get("tasks_by_status"), dict)
