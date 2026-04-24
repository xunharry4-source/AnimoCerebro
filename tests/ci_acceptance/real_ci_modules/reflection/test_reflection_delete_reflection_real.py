from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_delete_reflection_real(real_ci_runtime) -> None:
    """功能：验证 delete_reflection 真实删除。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    rec = runtime.reflection_service.record_nine_question_reflection(
        subject=f"q1-del-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": "old"},
    )
    ok = runtime.reflection_service.delete_reflection(rec.reflection_id)
    assert ok is True
    rows = runtime.reflection_service.list_reflections({})
    assert all(item.reflection_id != rec.reflection_id for item in rows), "删除后仍能查询到该 reflection"
