from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_audit_query_flows_real(real_ci_runtime) -> None:
    """功能：验证 query_flows 返回列表。"""
    suffix = unique_suffix()
    out = real_ci_runtime.audit_service.record_nine_question_audit(
        question_id="q1",
        module_id="query_flows",
        summary=f"flow-summary-{suffix}",
        payload={"suffix": suffix},
        trace_id=f"flow-trace-{suffix}",
        session_id=f"flow-sess-{suffix}",
        turn_id=f"flow-turn-{suffix}",
        source="tests.ci_acceptance",
    )
    rows = real_ci_runtime.audit_service.query_flows(limit=50)
    assert any(str(out["audit_id"]) in str(item) for item in rows), "query_flows 未查询到刚写入的 flow"
