from __future__ import annotations

from zentex.upgrade.ledger import UpgradeMemoryRecord

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_ingest_upgrade_memory_record_real(real_ci_runtime) -> None:
    """功能：验证 ingest_upgrade_memory_record 成功投影到可查询记忆。"""
    suffix = unique_suffix()
    record = UpgradeMemoryRecord(
        record_id=f"rec-{suffix}",
        trace_id=f"trace-{suffix}",
        request_id=f"req-{suffix}",
        target_kind="strategy",
        action="promote",
        target_id=f"target-{suffix}",
        title=f"upgrade-{suffix}",
        event_type="upgrade_completed",
        summary=f"upgrade-summary-{suffix}",
        current_status="completed",
        current_progress=100,
        current_version="v1",
        success_summary=f"success-{suffix}",
    )
    real_ci_runtime.memory_service.ingest_upgrade_memory_record(record)
    rows = real_ci_runtime.memory_service.query_managed_records(limit=200, trace_id=record.trace_id)
    assert any(getattr(item, "trace_id", "") == record.trace_id for item in rows), "升级记录投影后未被查询命中"
