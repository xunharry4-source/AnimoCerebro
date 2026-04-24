from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_list_audit_events_real(real_ci_runtime) -> None:
    """功能：验证 list_audit_events 返回审计事件列表，并命中新增记忆事件。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"audit-{suffix}",
        content=f"audit-content-{suffix}",
        source="tests",
        trace_id=f"trace-{suffix}",
        tags=["q1", suffix],
    )
    rows = real_ci_runtime.memory_service.list_audit_events(limit=200)
    assert isinstance(rows, list)
    assert any(rec.memory_id in str(item) for item in rows), "审计事件中未出现新增记忆"
