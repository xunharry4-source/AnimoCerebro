from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_memory_maintenance_real(real_ci_runtime) -> None:
    """功能：验证 reflection service 可用记忆数据执行手动整理。"""
    suffix = unique_suffix()
    remembered = real_ci_runtime.memory_service.remember(
        title=f"reflection-maint-{suffix}",
        content=f"reflection memory maintenance content {suffix}",
        summary=f"reflection summary {suffix}",
        source="tests",
        tags=["maint", suffix],
    )

    result = real_ci_runtime.reflection_service.trigger_memory_aware_maintenance(operator="ci")
    assert result.used_memory_count >= 1
    assert result.generated_reflection_id

    record = real_ci_runtime.reflection_service.get_reflection(result.generated_reflection_id)
    assert record.metadata.get("source") == "memory_aware_maintenance"
    assert "tier_pressure" in record.context
    assert isinstance(record.context.get("tier_pressure"), dict)
    assert "layer_distribution" in record.context
    assert remembered.memory_id in (record.context.get("memory_ids") or [])
