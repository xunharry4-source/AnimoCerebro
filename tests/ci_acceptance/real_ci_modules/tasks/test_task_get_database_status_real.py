from __future__ import annotations


def test_task_get_database_status_real(real_ci_runtime) -> None:
    """功能：验证 get_database_status 返回数据库状态。"""
    out = real_ci_runtime.task_service.get_database_status()
    assert isinstance(out, dict)
    assert "available" in out
    assert "enabled" in out
    assert "message" in out
