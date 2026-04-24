from __future__ import annotations


def test_memory_list_projection_failures_real(real_ci_runtime) -> None:
    """功能：验证 list_projection_failures 返回列表。"""
    rows = real_ci_runtime.memory_service.list_projection_failures()
    assert isinstance(rows, list)
    assert all(isinstance(item, str) for item in rows), "projection_failures 元素必须为字符串"
