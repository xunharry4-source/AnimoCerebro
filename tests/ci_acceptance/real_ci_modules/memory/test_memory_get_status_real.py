from __future__ import annotations


def test_memory_get_status_real(real_ci_runtime) -> None:
    """功能：验证 get_status 返回状态结构。"""
    s = real_ci_runtime.memory_service.get_status()
    assert isinstance(s, dict)
    assert s.get("storage_root"), "缺少 storage_root"
    assert isinstance(s.get("backend_status"), list), "backend_status 应为列表"
    assert isinstance(s.get("health_snapshot"), dict), "health_snapshot 应为字典"
    assert isinstance(s.get("health_status"), str) and s.get("health_status"), "health_status 应为非空字符串"
