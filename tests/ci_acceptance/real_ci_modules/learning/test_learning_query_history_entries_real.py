from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_learning_query_history_entries_real(real_ci_runtime) -> None:
    """功能：验证 query_history_entries 对外查询。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.learning_service.record_nine_question_learning(
        question_id="q1",
        learning_kind="query_history_entries",
        detail={"summary": f"learning-query-summary-{suffix}", "question_driver_refs": ["q1"]},
        trace_id=f"learning-query-trace-{suffix}",
    )
    rows = real_ci_runtime.learning_service.query_history_entries(limit=20)
    assert any(rec.trace_id in str(item) for item in rows), "query_history_entries 未查询到刚写入的学习记录"
