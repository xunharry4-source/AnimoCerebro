from __future__ import annotations

from zentex.reflection.service import get_reflection_service


def test_reflection_get_reflection_service_real() -> None:
    """功能：验证 get_reflection_service 工厂可用。"""
    svc = get_reflection_service()
    assert hasattr(svc, "list_reflections")
