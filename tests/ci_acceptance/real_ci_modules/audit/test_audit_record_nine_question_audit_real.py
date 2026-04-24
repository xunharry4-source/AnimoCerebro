from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_audit_record_nine_question_audit_real(real_ci_runtime) -> None:
    """功能：验证 record_nine_question_audit 真实写入。"""
    suffix = unique_suffix()
    out = real_ci_runtime.audit_service.record_nine_question_audit(
        question_id="q1",
        module_id="ci_audit",
        summary=f"audit-{suffix}",
        payload={"k": suffix},
        trace_id=f"trace-{suffix}",
        session_id=f"sess-{suffix}",
        turn_id=f"turn-{suffix}",
        source="tests.ci_acceptance",
    )
    assert str(out.get("audit_id") or "").strip()
