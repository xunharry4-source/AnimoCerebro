from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_learning_overall_record_real(real_ci_runtime) -> None:
    """功能：验证 learning 服务自动写入整体记录。"""
    suffix = unique_suffix()
    marker = f"learning-overall-{suffix}"
    record = real_ci_runtime.learning_service.record_nine_question_learning(
        question_id="q1",
        learning_kind="summary",
        detail={"summary": marker, "module_id": "ci_real_learning"},
        trace_id=f"trace-{suffix}",
    )

    rows = real_ci_runtime.learning_service.query_overall_records(limit=50, trace_id=record.trace_id)
    assert rows, "learning 整体记录为空"
    matched = rows[0]
    assert matched.status == "completed"
    assert matched.direction == "nine_question_integration"
    assert marker in matched.summary
