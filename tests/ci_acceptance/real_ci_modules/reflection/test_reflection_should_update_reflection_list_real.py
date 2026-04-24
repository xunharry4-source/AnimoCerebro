from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_should_update_reflection_list_real(real_ci_runtime) -> None:
    """功能：验证 should_update_reflection_list 可执行判定。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-judge-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "x"},
    )
    ok = runtime.reflection_service.should_update_reflection_list(rec)
    # 该方法为策略判定：返回必须是布尔值，且同一输入重复调用结果应稳定。
    assert isinstance(ok, bool)
    ok2 = runtime.reflection_service.should_update_reflection_list(rec)
    assert ok2 is ok
