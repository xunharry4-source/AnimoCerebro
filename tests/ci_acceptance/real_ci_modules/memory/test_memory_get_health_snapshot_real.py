from __future__ import annotations


def test_memory_get_health_snapshot_real(real_ci_runtime) -> None:
    """功能：验证 get_health_snapshot 返回字典。"""
    snap = real_ci_runtime.memory_service.get_health_snapshot()
    assert isinstance(snap, dict)
    assert isinstance(snap.get("health_status"), str), "health_status 字段缺失或类型错误"
