from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_claim_task_real(real_ci_runtime) -> None:
    """功能：验证 claim_task 认领任务。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="claim"))
    out = await real_ci_runtime.task_service.claim_task(task.task_id, handler_id="handler-1")
    assert out.target_id == "handler-1"
