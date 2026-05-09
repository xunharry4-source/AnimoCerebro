from __future__ import annotations

from zentex.reflection.models import ReflectionType


def test_reflection_overall_record_real(real_ci_runtime) -> None:
    """功能：验证生成反思后自动产出整体记录摘要。"""
    svc = real_ci_runtime.reflection_service
    record = svc.generate_reflection(
        subject="ci-overall-reflection",
        reflection_type=ReflectionType.DECISION_REFLECTION,
        context={"question_id": "q1", "summary": "overall-summary-marker"},
    )

    rows = svc.list_overall_records(limit=20, trace_id=record.trace_id)
    assert rows, "整体记录列表为空"
    assert any(item.reflection_id == record.reflection_id for item in rows), "未命中对应反思的整体记录"
    matched = next(item for item in rows if item.reflection_id == record.reflection_id)
    assert matched.subject == "ci-overall-reflection"
    assert "overall-summary-marker" in matched.summary
