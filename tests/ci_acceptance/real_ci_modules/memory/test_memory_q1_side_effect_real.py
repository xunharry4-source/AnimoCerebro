from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import run_q1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_q1_side_effect_real(real_ci_runtime) -> None:
    """功能：验证 Q1 真实执行后，记忆结果在记忆/反思/审计模块均可查询。"""
    runtime = real_ci_runtime

    # 真实业务链路执行 Q1（必须依赖外部 LLM），不手工写记忆数据。
    await run_q1(runtime, timeout_seconds=600.0)

    records = runtime.memory_service.query_managed_records(limit=200)
    q1_records = [item for item in records if "q1" in str(item).lower()]
    assert q1_records, "memory_records 未发现 q1 关联记录"
    assert any(str(getattr(item, "memory_id", "")).strip() for item in q1_records), "q1 记忆记录缺少 memory_id"

    # 跨模块校验1：反思模块也必须可查询到 q1 关联数据。
    reflections = runtime.reflection_service.list_reflections({})
    assert any("q1" in str(item).lower() for item in reflections), "reflection 模块未查询到 q1 关联记录"

    # 跨模块校验2：审计模块 flow 中应存在 nine_questions 的 completed 记录。
    flows = runtime.audit_service.query_flows(limit=200, flow_type="nine_questions", status="completed")
    assert flows, "audit flow 未发现 nine_questions completed 记录"
