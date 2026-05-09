from __future__ import annotations

from zentex.memory.service import get_memory_service, get_service


def test_memory_get_service_real() -> None:
    """功能：验证 memory service 工厂对外可用。"""
    s1 = get_memory_service()
    s2 = get_service()
    assert s1 is s2, "memory 两个工厂入口应返回同一实例"
    assert hasattr(s1, "remember"), "memory_service 缺少对外写入方法 remember"
