from __future__ import annotations

from zentex.reflection.models import ReflectionType


def test_reflection_get_metrics_real(real_ci_runtime) -> None:
    """功能：验证 get_metrics 可返回指标。"""
    # 输入/动作：先真实写入一条反思，再获取 metrics。
    rec = real_ci_runtime.reflection_service.record_nine_question_reflection(
        subject="metrics-q1",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "metrics"},
    )
    assert rec.reflection_id
    m = real_ci_runtime.reflection_service.get_metrics()
    # 预期：指标对象字段完整，且总数不小于 1。
    assert m.total_reflections >= 1
    assert isinstance(m.reflections_by_type, dict)
    assert m.calculated_at is not None
