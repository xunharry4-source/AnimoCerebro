from __future__ import annotations

def test_learning_get_status_real(real_ci_runtime) -> None:
    """功能：验证 get_status 返回状态结构。"""
    status = real_ci_runtime.learning_service.get_status(limit=20)
    assert isinstance(status, dict)
    assert "status" in status or "entries" in status or "trace_id" in status
