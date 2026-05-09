from __future__ import annotations


def test_task_save_state_real(real_ci_runtime) -> None:
    """功能：验证 save_state 对外行为。"""
    assert real_ci_runtime.task_service.save_state() is True
