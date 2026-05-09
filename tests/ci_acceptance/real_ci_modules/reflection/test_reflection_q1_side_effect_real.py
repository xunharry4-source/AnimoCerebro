from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import run_q1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reflection_q1_side_effect_real(real_ci_runtime) -> None:
    """功能：验证 Q1 真实执行后，反思结果在反思/记忆/审计模块均可查询。"""
    runtime = real_ci_runtime

    # 真实业务链路执行 Q1，不手工写反思数据。
    await run_q1(runtime, timeout_seconds=240.0)

    reflections = runtime.reflection_service.list_reflections({})
    q1_records = [
        item
        for item in reflections
        if (
            "q1" in str(getattr(item, "subject", "")).lower()
            or "q1" in str((getattr(item, "context", {}) or {}).get("question_id", "")).lower()
        )
    ]
    assert q1_records, "reflection_records 未发现 q1 关联记录"
    assert all(str(item.reflection_id).strip() for item in q1_records), "q1 反思记录缺少 reflection_id"

    # 跨模块校验1：记忆模块可查询到 q1 相关内容，证明反思链路结果可被外部检索。
    memory_rows = runtime.memory_service.query_managed_records(limit=300)
    assert any("q1" in str(item).lower() for item in memory_rows), "memory 模块未查询到 q1 关联数据"

    # 跨模块校验2：审计模块 flow 健康查询中必须出现 nine_questions 完成记录。
    flows = runtime.audit_service.query_flows(limit=200, flow_type="nine_questions", status="completed")
    assert flows, "audit flow 未发现 nine_questions completed 记录"
