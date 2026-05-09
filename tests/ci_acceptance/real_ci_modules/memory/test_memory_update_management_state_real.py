from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_update_management_state_real(real_ci_runtime) -> None:
    """功能：验证 update_management_state 更新治理状态。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(title=f"ums-{suffix}", content="x", source="tests", tags=["q1"])
    out = real_ci_runtime.memory_service.update_management_state(
        rec.memory_id,
        status="active",
        visibility="internal",
        trust_level="verified",
        operator="ci",
        reason="ci",
    )
    assert out.trust_level == "verified"
    queried = real_ci_runtime.memory_service.get_record(rec.memory_id)
    assert queried is not None, "更新后查询不到记录"
    assert queried.trust_level == "verified", "更新后查询结果 trust_level 不匹配"
    assert queried.visibility == "internal", "更新后查询结果 visibility 不匹配"
