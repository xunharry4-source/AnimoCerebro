from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.tasks.dispatch.errors import NoMatchingExecutorError
from zentex.tasks.dispatch.router_impl import UnifiedTaskRouter
from zentex.tasks.models import SubtaskIntent, TaskStatus, TaskType


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
async def test_dispatch_router_no_matching_executor_raises_business_error_not_validation_error() -> None:
    task_id = f"no-executor-{unique_suffix()}"
    subtask = SubtaskIntent(
        local_id=task_id,
        title="route q8 next self task",
        objective="dispatch a Q8 next_self_tasks item only when a real executor exists",
        task_type=TaskType.COGNITIVE_STEP,
        content="requires q8 next_self_tasks executor",
        required_capabilities=["nine-questions", "q8", "next_self_tasks"],
    )
    router = UnifiedTaskRouter(plugin_layer=None)

    with pytest.raises(NoMatchingExecutorError) as exc_info:
        await router.get_dispatch_decision(subtask, task_id=task_id)

    assert exc_info.value.task_id == task_id
    assert exc_info.value.required_capabilities == ["nine-questions", "q8", "next_self_tasks"]
    assert "selected_executor" not in str(exc_info.value)
    assert router._router_decisions == []


@pytest.mark.asyncio
async def test_worker_blocks_unroutable_q8_next_self_task_and_persists_queryable_reason(real_ci_runtime) -> None:
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(
        {
            "title": f"q8-next-self-unroutable-{suffix}",
            "task_type": "cognitive_step",
            "priority": "critical",
            "originator_id": "ci_real_dispatch",
            "idempotency_key": f"q8-next-self-unroutable-{suffix}",
            "remarks": "Verify no matching executor is persisted as a dispatch block, not hidden fallback.",
            "tags": ["nine-questions", "q8", "next_self_tasks"],
            "metadata": {
                "source_module": "q8_what_should_i_do_now",
                "queue_name": "next_self_tasks",
                "test_suffix": suffix,
            },
        }
    )

    try:
        stats, queried = await _run_worker_until_task_status(
            real_ci_runtime.task_service,
            task.task_id,
            TaskStatus.BLOCKED,
        )

        assert stats["tasks_dispatched"] >= 1
        assert stats["tasks_blocked"] >= 1
        assert queried.metadata["dispatch_failure"]["reason"] == "no_matching_executor"
        assert queried.metadata["dispatch_failure"]["required_capabilities"] == [
            "nine-questions",
            "q8",
            "next_self_tasks",
        ]
        assert "No matching executor found" in queried.metadata["dispatch_failure"]["message"]

        raw = real_ci_runtime.task_service._task_dao.get_task(task.task_id)
        assert raw["status"] == "blocked"
        assert "No matching executor found" in raw["last_error"]
        assert raw["dispatch_plugin_id"] is None
    finally:
        real_ci_runtime.task_service.bulk_delete([task.task_id], force=True)
