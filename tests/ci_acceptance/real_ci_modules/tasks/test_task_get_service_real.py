from __future__ import annotations

from zentex.tasks.service import get_service


def test_task_get_service_real() -> None:
    """功能：验证 task get_service 工厂可用。"""
    s1 = get_service()
    s2 = get_service()
    assert s1 is s2, "get_service 应返回单例"
    assert hasattr(s1, "create_task"), "任务服务应暴露 create_task"
