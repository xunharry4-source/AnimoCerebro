from __future__ import annotations


class _DummyAdapter:
    pass


def test_memory_bind_episodic_adapter_real(real_ci_runtime) -> None:
    """功能：验证 bind_episodic_adapter 可绑定适配器。"""
    adapter = _DummyAdapter()
    real_ci_runtime.memory_service.bind_episodic_adapter(adapter)
    bound = real_ci_runtime.memory_service._internal_service  # noqa: SLF001
    assert bound._episodic_sink is adapter, "bind_episodic_adapter 未绑定 episodic sink"
    assert bound._episodic_recall_client is adapter, "bind_episodic_adapter 未绑定 episodic recall client"
