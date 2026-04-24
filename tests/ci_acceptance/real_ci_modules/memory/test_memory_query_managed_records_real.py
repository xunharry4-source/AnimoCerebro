from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_query_managed_records_real(real_ci_runtime) -> None:
    """功能：验证 query_managed_records 查询命中新写入记录。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"query-managed-{suffix}",
        content=f"query-managed-content-{suffix}",
        source="tests",
        trace_id=f"trace-{suffix}",
        tags=["q1", suffix],
    )
    rows = real_ci_runtime.memory_service.query_managed_records(limit=200, trace_id=rec.trace_id)
    assert isinstance(rows, list)
    assert any(getattr(item, "memory_id", "") == rec.memory_id for item in rows), "query_managed_records 未命中新纪录"
