from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import run_q1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_learning_q1_side_effect_real(real_ci_runtime) -> None:
    """功能：验证 Q1 真实执行后，学习结果在学习/记忆/审计模块均可查询。"""
    runtime = real_ci_runtime

    # 真实业务链路执行 Q1（必须依赖外部 LLM），不手工构造学习数据。
    await run_q1(runtime, timeout_seconds=600.0)

    entries = runtime.learning_service.list_history_entries(limit=300)
    q1_entries = [item for item in entries if "q1" in str(item).lower()]
    assert q1_entries, "learning_entries 未发现 q1 关联记录"
    assert any("nine_question" in str(item).lower() for item in q1_entries), "q1 学习记录缺少 nine_question 语义标识"

    # 跨模块校验1：记忆模块应能查到 q1 相关记录，验证学习输出可被跨模块消费。
    memory_rows = runtime.memory_service.query_managed_records(limit=300)
    assert any("q1" in str(item).lower() for item in memory_rows), "memory 模块未查询到 q1 学习关联数据"

    # 跨模块校验2：审计模块 flow 中应存在 nine_questions 的 completed 记录。
    flows = runtime.audit_service.query_flows(limit=200, flow_type="nine_questions", status="completed")
    assert flows, "audit flow 未发现 nine_questions completed 记录"
