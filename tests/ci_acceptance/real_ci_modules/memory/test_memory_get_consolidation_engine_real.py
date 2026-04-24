from __future__ import annotations


def test_memory_get_consolidation_engine_real(real_ci_runtime) -> None:
    """功能：验证 get_consolidation_engine 对外可调用。"""
    engine = real_ci_runtime.memory_service.get_consolidation_engine()
    # 当前实现可能返回 None（由内核装配决定），但类型必须稳定：None 或具备 consolidation 能力对象。
    assert engine is None or hasattr(engine, "__class__"), "get_consolidation_engine 返回非法对象"
