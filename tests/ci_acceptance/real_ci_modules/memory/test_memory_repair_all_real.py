from __future__ import annotations


def test_memory_repair_all_real(real_ci_runtime) -> None:
    """功能：验证 repair_all 可调用。"""
    rows = real_ci_runtime.memory_service.repair_all()
    assert isinstance(rows, list)
    # 真实性依据：返回元素应为修复结果对象/字典，而不是空占位布尔值。
    for item in rows[:3]:
        assert hasattr(item, "model_dump") or isinstance(item, dict) or isinstance(item, str)
