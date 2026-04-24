from __future__ import annotations


def test_memory_backfill_upgrade_memory_records_real(real_ci_runtime) -> None:
    """功能：验证 backfill_upgrade_memory_records 可调用。"""
    before = real_ci_runtime.memory_service.list_projection_failures()
    real_ci_runtime.memory_service.backfill_upgrade_memory_records([])
    after = real_ci_runtime.memory_service.list_projection_failures()
    assert after == before, "空 backfill_upgrade_memory_records 不应改变 projection_failures"
