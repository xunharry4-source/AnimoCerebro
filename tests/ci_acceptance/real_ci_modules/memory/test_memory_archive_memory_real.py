from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_archive_memory_real(real_ci_runtime) -> None:
    """功能：验证 archive_memory 归档。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(title=f"arc-{suffix}", content="x", source="tests", tags=["q1"])
    out = real_ci_runtime.memory_service.archive_memory(rec.memory_id, reason="ci", operator="ci")
    assert out.status == "archived"
    queried = real_ci_runtime.memory_service.get_record(rec.memory_id)
    assert queried is not None, "归档后查询不到记录"
    assert queried.status == "archived", "归档后查询状态不一致"
