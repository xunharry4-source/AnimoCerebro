from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_verify_record_real(real_ci_runtime) -> None:
    """功能：验证 verify_record 校验记录。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(title=f"vrf-{suffix}", content="x", source="tests", tags=["q1"])
    out = real_ci_runtime.memory_service.verify_record(rec.memory_id)
    queried = real_ci_runtime.memory_service.get_record(rec.memory_id)
    assert queried is not None
    assert queried.memory_id == rec.memory_id
    assert out is not None
