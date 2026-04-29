from __future__ import annotations

import json
import logging

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.tasks.models import TaskStatus


async def _run_worker_until_task_status(
    task_service,
    task_id: str,
    expected_status: TaskStatus,
    *,
    max_cycles: int = 8,
) -> tuple[dict, object]:
    last_stats: dict = {}
    for _ in range(max_cycles):
        last_stats = await task_service.run_worker_cycle()
        queried = task_service.get_task(task_id)
        assert queried is not None
        if queried.status == expected_status:
            return last_stats, queried

    raw = task_service._task_dao.get_task(task_id)
    pytest.fail(
        f"task {task_id} did not reach {expected_status.value} after {max_cycles} real worker cycles; "
        f"last_stats={last_stats}, raw_status={raw.get('status') if raw else None}, "
        f"raw_last_error={raw.get('last_error') if raw else None}"
    )


@pytest.mark.asyncio
async def test_task_run_worker_cycle_real(real_ci_runtime) -> None:
    """功能：验证 run_worker_cycle 返回结构。"""
    out = await real_ci_runtime.task_service.run_worker_cycle()
    assert isinstance(out, dict)
    assert "tasks_dispatched" in out or "error" in out


@pytest.mark.asyncio
async def test_task_run_worker_cycle_blocks_q8_next_self_task_when_no_executor_matches(real_ci_runtime) -> None:
    """功能：验证无匹配 executor 时任务真实落库为 blocked，不能 fallback 或隐藏错误。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(
        {
            "title": f"q8-next-self-no-executor-{suffix}",
            "task_type": "cognitive_step",
            "priority": "critical",
            "originator_id": "ci_real_dispatch_existing_test",
            "idempotency_key": f"q8-next-self-no-executor-{suffix}",
            "remarks": "This task intentionally requires a missing q8 next_self_tasks executor.",
            "tags": ["nine-questions", "q8", "next_self_tasks"],
            "metadata": {
                "source_module": "q8_what_should_i_do_now",
                "queue_name": "next_self_tasks",
                "test_suffix": suffix,
            },
        }
    )

    try:
        out, queried = await _run_worker_until_task_status(
            real_ci_runtime.task_service,
            task.task_id,
            TaskStatus.BLOCKED,
        )

        assert isinstance(out, dict)
        assert out["tasks_dispatched"] >= 1
        assert out["tasks_blocked"] >= 1

        assert queried.metadata["dispatch_failure"]["reason"] == "no_matching_executor"
        assert queried.metadata["dispatch_failure"]["required_capabilities"] == [
            "nine-questions",
            "q8",
            "next_self_tasks",
        ]
        assert "No matching executor found" in queried.metadata["dispatch_failure"]["message"]

        raw = real_ci_runtime.task_service._task_dao.get_task(task.task_id)
        assert raw["status"] == "blocked"
        assert raw["dispatch_plugin_id"] is None
        assert "No matching executor found" in raw["last_error"]
    finally:
        real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)


@pytest.mark.asyncio
async def test_task_run_worker_cycle_updates_router_credit_after_real_plugin_success(
    real_ci_runtime,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """功能：真实执行插件后必须回写任务结果并更新 router credit。"""
    suffix = unique_suffix()
    plugin_id = "task_result_normalizer"
    router = real_ci_runtime.task_service._dispatch_manager._router
    executor = real_ci_runtime.task_service._dispatch_manager._executor
    before_credit = executor._plugin_credit_scores.get(plugin_id, 1.0)

    task = await real_ci_runtime.task_service.create_task(
        {
            "title": f"result-normalizer-success-{suffix}",
            "task_type": "system_action",
            "priority": "critical",
            "originator_id": "ci_real_worker_success",
            "idempotency_key": f"result-normalizer-success-{suffix}",
            "remarks": "Dispatch to the real task_result_normalizer plugin and persist the result.",
            "tags": ["task.result_normalization"],
            "metadata": {
                "source_module": "ci_real_worker_success",
                "test_suffix": suffix,
            },
        }
    )

    try:
        with caplog.at_level(logging.WARNING):
            stats, queried = await _run_worker_until_task_status(
                real_ci_runtime.task_service,
                task.task_id,
                TaskStatus.DONE,
            )

        assert stats["tasks_dispatched"] >= 1
        assert stats["tasks_succeeded"] >= 1
        assert "error" not in stats
        assert queried.status == TaskStatus.DONE
        assert not [
            record
            for record in caplog.records
            if "Could not update router credit score" in record.getMessage()
            or "Plugin instance not found" in record.getMessage()
        ]

        raw = real_ci_runtime.task_service._task_dao.get_task(task.task_id)
        assert raw["status"] == "done"
        assert raw["dispatch_plugin_id"] == plugin_id
        assert raw["last_error"] is None
        assert raw["execution_output"]
        output = json.loads(raw["execution_output"])
        assert output["normalized"] is True
        assert output["status"] == "done"
        assert output["source_kind"] == "generic"

        matching_decisions = [
            decision
            for decision in router._router_decisions
            if decision.task_id == task.task_id
        ]
        assert matching_decisions
        assert matching_decisions[-1].selected_executor.executor_id == plugin_id
        assert executor._plugin_credit_scores[plugin_id] > before_credit
    finally:
        real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)


@pytest.mark.asyncio
async def test_task_run_worker_cycle_executes_local_system_with_valid_action_intent_real(
    real_ci_runtime,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """功能：execution_local_system 必须接收合法 ActionIntent 并真实写回执行回执。"""
    suffix = unique_suffix()
    plugin_id = "execution_local_system"
    task = await real_ci_runtime.task_service.create_task(
        {
            "title": f"stats-{suffix}",
            "task_type": "system_action",
            "priority": "critical",
            "originator_id": "ci_real_local_system",
            "idempotency_key": f"local-system-{suffix}",
            "remarks": f"stats-{suffix}",
            "tags": ["execution.system"],
            "metadata": {
                "source_module": "ci_real_local_system",
                "test_suffix": suffix,
            },
        }
    )

    try:
        with caplog.at_level(logging.ERROR):
            stats, queried = await _run_worker_until_task_status(
                real_ci_runtime.task_service,
                task.task_id,
                TaskStatus.DONE,
            )

        assert stats["tasks_dispatched"] >= 1
        assert stats["tasks_succeeded"] >= 1
        assert "error" not in stats
        assert queried.status == TaskStatus.DONE
        assert not [
            record
            for record in caplog.records
            if "Plugin execution_local_system execution failed" in record.getMessage()
            or "validation errors for ActionIntent" in record.getMessage()
        ]

        raw = real_ci_runtime.task_service._task_dao.get_task(task.task_id)
        assert raw["status"] == "done"
        assert raw["dispatch_plugin_id"] == plugin_id
        assert raw["last_error"] is None
        assert raw["execution_output"]
        output = json.loads(raw["execution_output"])
        assert output["status"] == "succeeded"
        assert output["execution_domain"] == "system"
        assert output["workspace"] is None
        assert isinstance(output["action_hash"], str)
        assert len(output["action_hash"]) == 64
    finally:
        real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)
