from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_strategy_cross_module_persistence_real(real_ci_runtime) -> None:
    """功能：验证任务策略写入后，任务/审计/记忆模块都能查询到一致结果。"""
    runtime = real_ci_runtime
    suffix = unique_suffix()
    marker = f"strategy-marker-{suffix}"

    # 输入：创建带“策略标识”的任务。
    task = await runtime.task_service.create_task(
        {
            **task_payload(suffix=suffix, title_prefix="strategy-task"),
            "metadata": {"source_module": "ci_real_tasks", "strategy_marker": marker},
            "remarks": f"strategy:{marker}",
        }
    )

    # 动作：更新策略元数据，形成可审计状态变化。
    await runtime.task_service.update_task_metadata(
        task.task_id,
        {"strategy_stage": "planned", "strategy_marker": marker},
        remarks=f"strategy-updated:{marker}",
    )

    # 预期1（任务模块）：查询必须命中同一任务与同一策略字段。
    queried_task = runtime.task_service.get_task(task.task_id)
    assert queried_task is not None
    assert queried_task.task_id == task.task_id
    assert queried_task.metadata.get("strategy_marker") == marker
    assert queried_task.metadata.get("strategy_stage") == "planned"

    # 预期2（审计模块）：任务审计事件同步后，应能通过 audit_service 查询命中。
    transcript_rows = runtime.task_service.transcript_store.query_by_session("task-management-audit", limit=500)
    task_rows = [entry for entry in transcript_rows if task.task_id in str(getattr(entry, "payload", {}))]
    assert task_rows, "task-management-audit 未记录该任务策略变更事件"
    runtime.audit_service.store.sync_from_transcript_entries(task_rows)
    audit_page = runtime.audit_service.query_audit_entries(page=1, page_size=200)
    assert any(task.task_id in str(item.trace_id) for item in audit_page.items), "audit_entries 未命中该任务策略事件"

    # 预期3（记忆模块）：将任务审计事件回填后，应能在记忆查询中命中策略标识。
    runtime.memory_service.backfill_transcript_entries(task_rows)
    memory_rows = runtime.memory_service.query_managed_records(limit=300)
    assert any(marker in str(item) for item in memory_rows), "memory 查询未命中任务策略标识"
