from __future__ import annotations

from zentex.common.flow_audit import FlowAudit


def test_audit_record_flow_end_real(real_ci_runtime) -> None:
    """功能：验证 record_flow_end 后可通过 query_flows 查到 completed 状态。"""
    svc = real_ci_runtime.audit_service
    audit = FlowAudit.new("nine_questions", source_module="tests.ci_acceptance.flow_end")

    svc.record_flow_start(audit)
    svc.record_flow_end(audit, status="completed")

    rows = svc.query_flows(limit=200, flow_type="nine_questions", status="completed")
    matched = [item for item in rows if item.get("audit_id") == audit.audit_id]
    assert matched, "record_flow_end 后 query_flows 未命中 completed 记录"
    assert matched[0].get("status") == "completed"
