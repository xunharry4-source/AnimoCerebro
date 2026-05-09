from __future__ import annotations

from zentex.learning.service import get_service, get_learning_service


def test_learning_get_service_real() -> None:
    """功能：验证 learning service 工厂对外可用。"""
    s1 = get_service()
    s2 = get_learning_service()
    assert s1 is s2, "learning 两个工厂入口应返回同一实例"
    assert hasattr(s1, "record_nine_question_learning"), "learning_service 缺少对外方法"
