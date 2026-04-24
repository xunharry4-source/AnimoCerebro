from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_list_managed_records_real(real_ci_runtime) -> None:
    """功能：验证 list_managed_records 必须返回并包含新增记录。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"managed-{suffix}",
        content=f"managed-content-{suffix}",
        source="tests",
        tags=["q1", suffix],
    )
    rows = real_ci_runtime.memory_service.list_managed_records(limit=200)
    assert isinstance(rows, list)
    matched = [item for item in rows if getattr(item, "memory_id", "") == rec.memory_id]
    assert matched, "管理列表中未出现新增记录"
    assert matched[0].title == f"managed-{suffix}"
