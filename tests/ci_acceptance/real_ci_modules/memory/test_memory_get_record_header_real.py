from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_get_record_header_real(real_ci_runtime) -> None:
    """功能：验证 get_record_header 查询头信息。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(title=f"hdr-{suffix}", content="x", source="tests", tags=["q1"])
    hdr = real_ci_runtime.memory_service.get_record_header(rec.memory_id)
    assert hdr is not None
    assert rec.memory_id in str(hdr), "header 中应包含 memory_id"
