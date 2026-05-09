from __future__ import annotations


def test_memory_list_initialization_failures_real(real_ci_runtime) -> None:
    """功能：验证 list_initialization_failures 返回列表。"""
    rows = real_ci_runtime.memory_service.list_initialization_failures()
    assert isinstance(rows, list)
    assert all(isinstance(item, str) for item in rows), "initialization_failures 元素必须为字符串"
