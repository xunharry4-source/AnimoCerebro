from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_audit_query_audit_entries_real(real_ci_runtime) -> None:
    """功能：验证 query_audit_entries 对外查询。"""
    suffix = unique_suffix()
    real_ci_runtime.audit_service.record_nine_question_audit(
        question_id="q1",
        module_id="query_audit_entries",
        summary=f"summary-{suffix}",
        payload={"suffix": suffix},
        trace_id=f"trace-{suffix}",
        session_id=f"sess-{suffix}",
        turn_id=f"turn-{suffix}",
        source="tests.ci_acceptance",
    )
    page = real_ci_runtime.audit_service.query_audit_entries(page=1, page_size=20)
    assert page.page >= 1 and page.page_size == 20
    assert any(f"trace-{suffix}" in str(item.trace_id) for item in page.items), "query_audit_entries 未查到刚写入审计记录"
