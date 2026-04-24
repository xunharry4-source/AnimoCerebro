from __future__ import annotations


def test_task_get_task_real(real_ci_runtime) -> None:
    """功能：验证 get_task 可处理空输入。"""
    assert real_ci_runtime.task_service.get_task("") is None
