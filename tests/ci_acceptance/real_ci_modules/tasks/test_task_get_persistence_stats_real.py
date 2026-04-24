from __future__ import annotations


def test_task_get_persistence_stats_real(real_ci_runtime) -> None:
    """功能：验证 get_persistence_stats 对外行为。"""
    out = real_ci_runtime.task_service.get_persistence_stats()
    assert out is None
