from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_audit_q1_side_effect_real(real_ci_runtime) -> None:
    """功能：验证 Q1 真实执行后会产生审计流记录。"""
    runtime = real_ci_runtime

    # 真实业务链路执行 Q1，不手工写审计数据。
    await runtime.nine_question_service.run_single("q1", timeout_seconds=90.0)

    flows = runtime.audit_service.query_flows(flow_type="nine_questions", limit=300)
    q1_flows = [item for item in flows if "q1" in str(item).lower()]
    assert q1_flows, "audit_flows 未发现 q1 关联记录"
    assert any(str(item.get("status") or "") in {"started", "completed"} for item in q1_flows if isinstance(item, dict)), (
        "q1 审计流缺少 started/completed 状态标记"
    )
