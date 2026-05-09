from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix

def test_learning_list_history_entries_real(real_ci_runtime) -> None:
    """功能：验证 list_history_entries 对外查询。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.learning_service.record_nine_question_learning(
        question_id="q1",
        learning_kind="list_history_entries",
        detail={"summary": f"learning-summary-{suffix}", "question_driver_refs": ["q1"]},
        trace_id=f"learning-trace-{suffix}",
    )
    rows = real_ci_runtime.learning_service.list_history_entries(limit=20)
    assert any(rec.trace_id in str(item) for item in rows), "list_history_entries 未查询到刚写入的学习记录"
