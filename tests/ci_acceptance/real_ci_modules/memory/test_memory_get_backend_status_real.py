from __future__ import annotations


def test_memory_get_backend_status_real(real_ci_runtime) -> None:
    """功能：验证 get_backend_status 返回结构化后端状态。"""
    rows = real_ci_runtime.memory_service.get_backend_status()
    assert isinstance(rows, list)
    if rows:
        first = rows[0]
        # 后端状态对象至少要能序列化出核心字段。
        if hasattr(first, "model_dump"):
            payload = first.model_dump()
        elif hasattr(first, "__dict__"):
            payload = dict(first.__dict__)
        else:
            payload = {"value": str(first)}
        assert "name" in payload or "backend" in payload
