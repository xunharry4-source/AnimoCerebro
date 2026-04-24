from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_verify_reflection_real(real_ci_runtime) -> None:
    """功能：验证 verify_reflection 更新治理状态。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-verify-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "x"},
    )
    out = runtime.reflection_service.verify_reflection(rec.reflection_id, verified_by="ci")
    assert str(out.verified_by) == "ci"
    queried = runtime.reflection_service.get_reflection(rec.reflection_id)
    assert str(queried.verified_by) == "ci", "verify_reflection 后查询到的 verified_by 不一致"
