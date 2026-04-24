from __future__ import annotations


def test_memory_trigger_manual_consolidation_real(real_ci_runtime) -> None:
    """功能：验证 memory service 可手动触发整理任务。"""
    handle = real_ci_runtime.memory_service.trigger_manual_consolidation(operator="ci")
    assert handle.cycle_id
    assert handle.lease_id

    engine = real_ci_runtime.memory_service.get_consolidation_engine()
    cycles = engine.list_cycles(cycle_id=handle.cycle_id)
    assert cycles, "manual consolidation 未进入 engine 周期列表"
    assert cycles[0].cycle_id == handle.cycle_id
