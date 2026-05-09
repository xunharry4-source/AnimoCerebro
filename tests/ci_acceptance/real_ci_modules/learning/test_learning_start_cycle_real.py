from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_learning_start_cycle_real(real_ci_runtime) -> None:
    """功能：验证 start_cycle 可启动学习周期（dry_run）。"""
    out = await real_ci_runtime.learning_service.start_cycle(
        direction="nine_question_integration",
        dry_run=True,
        load_factor=0.0,
    )
    assert str(out.status).strip()
