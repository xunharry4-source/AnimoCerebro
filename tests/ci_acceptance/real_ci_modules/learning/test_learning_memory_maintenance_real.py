from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_learning_memory_maintenance_real(real_ci_runtime) -> None:
    """功能：验证 learning service 可用记忆和反思数据执行手动整理。"""
    suffix = unique_suffix()
    real_ci_runtime.memory_service.remember(
        title=f"learning-maint-{suffix}",
        content=f"learning memory maintenance content {suffix}",
        summary=f"learning summary {suffix}",
        source="tests",
        tags=["learn-maint", suffix],
    )
    real_ci_runtime.reflection_service.record_nine_question_reflection(
        subject=f"learning-reflection-{suffix}",
        reflection_type=ReflectionType.LEARNING_REFLECTION,
        context={"summary": f"reflection-from-memory-{suffix}", "question_id": "q1"},
        trace_id=f"reflection-trace-{suffix}",
    )

    result = real_ci_runtime.learning_service.trigger_memory_aware_maintenance(operator="ci")
    assert result.used_memory_count >= 1
    assert result.used_reflection_count >= 1

    rows = real_ci_runtime.learning_service.query_overall_records(limit=50, trace_id=result.trace_id)
    assert rows, "learning maintenance 未写入 overall record"
    assert rows[0].direction == "memory_maintenance"
    assert rows[0].status == "completed"
    assert rows[0].detail.get("cross_module_pressure") is not None
    assert rows[0].detail.get("layer_distribution") is not None
