from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_update_reflection_real(real_ci_runtime) -> None:
    """功能：验证 update_reflection 真实更新。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-update-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "old"},
    )
    updated = runtime.reflection_service.update_reflection(rec.reflection_id, {"context": {"question_id": "q1", "summary": "new"}})
    assert updated.context.get("summary") == "new"
    queried = runtime.reflection_service.get_reflection(rec.reflection_id)
    assert queried.context.get("summary") == "new", "更新后查询结果未反映最新 summary"
