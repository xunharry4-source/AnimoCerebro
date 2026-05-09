from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_get_reflection_real(real_ci_runtime) -> None:
    """功能：验证 get_reflection 查询。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-get-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "x"},
    )
    got = runtime.reflection_service.get_reflection(rec.reflection_id)
    assert got.reflection_id == rec.reflection_id
