from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_task_run_worker_cycle_real(real_ci_runtime) -> None:
    """功能：验证 run_worker_cycle 返回结构。"""
    out = await real_ci_runtime.task_service.run_worker_cycle()
    assert isinstance(out, dict)
    assert "tasks_dispatched" in out or "error" in out
