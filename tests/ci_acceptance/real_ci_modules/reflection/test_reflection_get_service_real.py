from __future__ import annotations

from zentex.reflection.service import get_service


def test_reflection_get_service_real() -> None:
    """功能：验证 reflection get_service 对外工厂可用。"""
    svc = get_service()
    assert svc is not None
    assert callable(getattr(svc, "list_reflections", None))
    assert callable(getattr(svc, "record_nine_question_reflection", None))
