from __future__ import annotations

def test_memory_get_sync_engine_real(real_ci_runtime) -> None:
    """功能：验证 get_sync_engine 返回同步引擎实例。"""
    engine = real_ci_runtime.memory_service.get_sync_engine()
    assert engine is not None
    assert hasattr(engine, "push")
    assert hasattr(engine, "pull")
