from __future__ import annotations

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_list_reflections_real(real_ci_runtime) -> None:
    """功能：验证 list_reflections 对外查询，并命中新写入数据。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.reflection_service.record_nine_question_reflection(
        subject=f"list-ref-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q1", "summary": f"sum-{suffix}"},
        trace_id=f"trace-{suffix}",
    )
    rows = real_ci_runtime.reflection_service.list_reflections({"trace_id": f"trace-{suffix}"})
    assert isinstance(rows, list), "reflection_rows 必须返回 list"
    assert any(item.reflection_id == rec.reflection_id for item in rows), "未查询到刚写入的 reflection"
