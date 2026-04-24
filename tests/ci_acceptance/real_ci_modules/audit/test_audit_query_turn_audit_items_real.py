from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_audit_query_turn_audit_items_real(real_ci_runtime) -> None:
    """功能：验证 query_turn_audit_items 对外查询。"""
    suffix = unique_suffix()
    real_ci_runtime.audit_service.record_nine_question_audit(
        question_id="q1",
        module_id="query_turn_audit_items",
        summary=f"turn-summary-{suffix}",
        payload={"suffix": suffix},
        trace_id=f"turn-trace-{suffix}",
        session_id=f"turn-sess-{suffix}",
        turn_id=f"turn-id-{suffix}",
        source="tests.ci_acceptance",
    )
    page = real_ci_runtime.audit_service.query_turn_audit_items(page=1, page_size=500)
    assert page.page >= 1 and page.page_size > 0
    assert any(f"turn-id-{suffix}" in str(item.turn_id) for item in page.items), "query_turn_audit_items 未查到目标 turn_id"
