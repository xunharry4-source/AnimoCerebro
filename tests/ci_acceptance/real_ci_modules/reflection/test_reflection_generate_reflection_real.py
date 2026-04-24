from __future__ import annotations

from zentex.reflection.models import ReflectionType


def test_reflection_generate_reflection_real(real_ci_runtime) -> None:
    """功能：验证 generate_reflection 对外方法，必须成功生成并可查询。"""
    svc = real_ci_runtime.reflection_service
    out = svc.generate_reflection(
        subject="ci-generate",
        reflection_type=ReflectionType.DECISION_REFLECTION,
        context={"question_id": "q1", "summary": "ci"},
    )
    assert out.reflection_id
    queried = svc.get_reflection(out.reflection_id)
    assert queried.reflection_id == out.reflection_id
    assert queried.reflection_type == ReflectionType.DECISION_REFLECTION
    assert queried.context.get("question_id") == "q1"
