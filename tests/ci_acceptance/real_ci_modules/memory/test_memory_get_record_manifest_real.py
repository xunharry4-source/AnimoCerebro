from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_get_record_manifest_real(real_ci_runtime) -> None:
    """功能：验证 get_record_manifest 查询清单。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(title=f"mft-{suffix}", content="x", source="tests", tags=["q1"])
    m = real_ci_runtime.memory_service.get_record_manifest(rec.memory_id)
    assert m is not None
    assert rec.memory_id in str(m), "manifest 中应包含 memory_id"
