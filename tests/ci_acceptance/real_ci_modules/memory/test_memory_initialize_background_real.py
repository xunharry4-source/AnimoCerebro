from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_memory_initialize_background_real(real_ci_runtime) -> None:
    """功能：验证 initialize_background 异步初始化。"""
    before = real_ci_runtime.memory_service.get_health_snapshot()
    await real_ci_runtime.memory_service.initialize_background()
    after = real_ci_runtime.memory_service.get_health_snapshot()
    assert isinstance(before.get("health_status"), str), "初始化前 health_status 格式异常"
    assert isinstance(after.get("health_status"), str), "初始化后 health_status 格式异常"
