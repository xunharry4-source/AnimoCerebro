from __future__ import annotations

from zentex.audit.service import get_service


def test_audit_get_service_real() -> None:
    """功能：验证 audit get_service 工厂可用。"""
    s1 = get_service()
    s2 = get_service()
    assert s1 is s2, "audit get_service 应返回单例"
    assert hasattr(s1, "record_nine_question_audit"), "audit_service 缺少关键对外方法"
