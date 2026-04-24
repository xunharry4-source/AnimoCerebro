from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_get_record_real(real_ci_runtime) -> None:
    """功能：验证 get_record 读取记录。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"get-{suffix}", content=f"x-{suffix}", source="tests", tags=["q1"]
    )
    got = real_ci_runtime.memory_service.get_record(rec.memory_id)
    assert got is not None and got.memory_id == rec.memory_id
    assert got.title == f"get-{suffix}"
    assert f"x-{suffix}" in str(getattr(got, "content", ""))
