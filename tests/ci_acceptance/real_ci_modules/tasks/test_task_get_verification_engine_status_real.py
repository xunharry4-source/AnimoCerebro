from __future__ import annotations


def test_task_get_verification_engine_status_real(real_ci_runtime) -> None:
    """功能：验证 get_verification_engine_status 返回状态。"""
    out = real_ci_runtime.task_service.get_verification_engine_status()
    assert isinstance(out, dict)
    assert "available" in out
    assert "message" in out
