from __future__ import annotations


def test_reflection_register_expectation_real(real_ci_runtime) -> None:
    """功能：验证 register_expectation 可注册期望。"""
    exp_id = real_ci_runtime.reflection_service.register_expectation(
        target_state="done",
        criteria=["a", "b"],
        confidence=0.6,
    )
    assert str(exp_id).strip()
