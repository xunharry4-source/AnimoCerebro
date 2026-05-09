from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_verification_records_real(real_ci_runtime) -> None:
    """功能：验证 get_verification_records 返回列表。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="veri-rec"))
    rows = real_ci_runtime.task_service.get_verification_records(task.task_id)
    assert isinstance(rows, list)
    for item in rows[:3]:
        assert isinstance(item, dict)
        assert item.get("task_id") == task.task_id
