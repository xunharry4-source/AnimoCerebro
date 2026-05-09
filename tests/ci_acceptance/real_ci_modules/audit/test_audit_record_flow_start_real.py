from __future__ import annotations

from zentex.common.flow_audit import FlowAudit


def test_audit_record_flow_start_end_real(real_ci_runtime) -> None:
    """功能：验证 record_flow_start 写入流程轨迹。"""
    svc = real_ci_runtime.audit_service
    audit = FlowAudit.new("nine_questions", source_module="tests.ci_acceptance")
    svc.record_flow_start(audit)
    rows = svc.query_flows(limit=100, flow_type="nine_questions")
    assert any(audit.audit_id in str(item) for item in rows)
