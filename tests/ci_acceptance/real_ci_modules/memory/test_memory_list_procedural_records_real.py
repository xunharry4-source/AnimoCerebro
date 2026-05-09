from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_list_procedural_records_real(real_ci_runtime) -> None:
    """功能：验证程序性层列表包含新写入记录。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"procedural-{suffix}",
        content=f"procedural-content-{suffix}",
        source="tests",
        layer="procedural",
        tags=["q1", suffix],
    )
    rows = real_ci_runtime.memory_service.list_procedural_records()
    assert isinstance(rows, list)
    assert any(getattr(item, "memory_id", "") == rec.memory_id for item in rows), "程序性层未包含新增记录"
