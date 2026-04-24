from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_mark_suspect_real(real_ci_runtime) -> None:
    """功能：验证 mark_suspect 可标记可疑并可查询。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-sus-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "x"},
    )
    out = runtime.reflection_service.mark_suspect(rec.reflection_id, reason="ci")
    assert out.reflection_id == rec.reflection_id
    queried = runtime.reflection_service.get_reflection(rec.reflection_id)
    assert queried.governance_status.value == "suspect"
