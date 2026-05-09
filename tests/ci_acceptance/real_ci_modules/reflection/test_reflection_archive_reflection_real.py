from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_archive_reflection_real(real_ci_runtime) -> None:
    """功能：验证 archive_reflection 可归档。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-arch-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "x"},
    )
    out = runtime.reflection_service.archive_reflection(rec.reflection_id)
    assert out.governance_status.value == "archived"
    queried = runtime.reflection_service.get_reflection(rec.reflection_id)
    assert queried.governance_status.value == "archived", "archive_reflection 后查询状态不一致"
