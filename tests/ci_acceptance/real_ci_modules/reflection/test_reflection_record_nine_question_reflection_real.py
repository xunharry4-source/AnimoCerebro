from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_record_nine_question_reflection_real(real_ci_runtime) -> None:
    """功能：验证 record_nine_question_reflection 真实写入。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-reflection-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": f"summary-{suffix}"},
        trace_id=f"trace-{suffix}",
    )
    assert rec.reflection_id
