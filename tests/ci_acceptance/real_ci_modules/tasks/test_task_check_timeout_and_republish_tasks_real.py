from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.tasks.models import TaskStatus


@pytest.mark.asyncio
async def test_task_check_timeout_blocks_in_progress_without_lease_and_persists_reason_real(
    real_ci_runtime,
    caplog,
) -> None:
    """功能：缺失 lease 的 in_progress 任务必须真实落库为 blocked，且原因可查询。"""
    caplog.set_level(logging.ERROR, logger="zentex.tasks.service")
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(
        {
            "title": f"timeout-missing-lease-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_timeout_recovery",
            "idempotency_key": f"timeout-missing-lease-{suffix}",
            "metadata": {
                "source_module": "ci_timeout_recovery",
                "test_suffix": suffix,
            },
        }
    )
    await real_ci_runtime.task_service.update_task_status(
        task.task_id,
        TaskStatus.IN_PROGRESS,
        remarks="simulate runtime task that lost lease metadata",
    )

    rows = await real_ci_runtime.task_service.check_timeout_and_republish_tasks(limit=1)

    row = next((item for item in rows if item["task_id"] == task.task_id), None)
    assert row is not None, "缺失 lease 的 in_progress 任务未返回恢复结果"
    assert row["republished"] is False
    assert row["new_status"] == "blocked"
    assert row["recovery_error"] == "missing_lease"
    assert row["required_action"] == "operator_review_missing_lease"
    assert "without lease metadata" in row["message"]
    assert row["timeout_seconds"] is None
    assert row["elapsed_seconds"] is None

    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None, "恢复后通过服务查询不到任务"
    assert queried.status == TaskStatus.BLOCKED
    timeout_recovery = queried.metadata["timeout_recovery"]
    assert timeout_recovery["timed_out"] is False
    assert timeout_recovery["recovery_error"] == "missing_lease"
    assert timeout_recovery["previous_status"] == "in_progress"
    assert timeout_recovery["recovery_source"] == "check_timeout_and_republish_tasks"
    assert timeout_recovery["required_action"] == "operator_review_missing_lease"
    assert "without lease metadata" in timeout_recovery["message"]
    assert queried.metadata["source_module"] == "ci_timeout_recovery"

    raw = real_ci_runtime.task_service._task_dao.get_task(task.task_id)
    assert raw is not None, "恢复后 DAO 查询不到任务"
    assert raw["status"] == "blocked"
    assert raw["metadata"]["timeout_recovery"]["recovery_error"] == "missing_lease"
    assert "without lease metadata" in raw["last_error"]
    assert raw["execution_finished_at"], "阻塞缺失 lease 任务时必须写入 execution_finished_at"

    repeated_rows = await real_ci_runtime.task_service.check_timeout_and_republish_tasks(limit=10)
    assert all(item["task_id"] != task.task_id for item in repeated_rows), (
        "缺失 lease 任务已经 blocked，第二次恢复扫描不应再次处理同一 task"
    )
    repeated_query = real_ci_runtime.task_service.get_task(task.task_id)
    assert repeated_query is not None
    assert repeated_query.status == TaskStatus.BLOCKED
    assert repeated_query.metadata["timeout_recovery"]["recovery_error"] == "missing_lease"
    assert task.task_id not in {
        item.task_id for item in real_ci_runtime.task_service.list_tasks(status=TaskStatus.IN_PROGRESS)
    }
    assert not any(
        record.levelno >= logging.ERROR
        and f"Task timeout recovery failed for {task.task_id}" in record.getMessage()
        for record in caplog.records
    ), "缺失 lease 任务不能继续记录 timeout recovery failed 错误日志"


@pytest.mark.asyncio
async def test_task_check_timeout_republishes_retriable_expired_lease_and_query_confirms_todo_real(
    real_ci_runtime,
) -> None:
    """功能：过期 lease 的可重试任务必须真实回到 todo，并保留过期证据。"""
    suffix = unique_suffix()
    heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=720)
    task = await real_ci_runtime.task_service.create_task(
        {
            "title": f"timeout-expired-lease-{suffix}",
            "task_type": "system_action",
            "originator_id": "ci_timeout_recovery",
            "idempotency_key": f"timeout-expired-lease-{suffix}",
            "contract": {"retriable": True},
            "metadata": {
                "source_module": "ci_timeout_recovery",
                "test_suffix": suffix,
                "lease": {
                    "status": "active",
                    "owner": "ci-timeout-test",
                    "acquired_at": heartbeat_at.isoformat(),
                    "heartbeat_at": heartbeat_at.isoformat(),
                    "timeout_seconds": 60,
                },
            },
        }
    )
    await real_ci_runtime.task_service.update_task_status(
        task.task_id,
        TaskStatus.IN_PROGRESS,
        remarks="simulate expired active lease",
    )

    rows = await real_ci_runtime.task_service.check_timeout_and_republish_tasks(limit=1)

    row = next((item for item in rows if item["task_id"] == task.task_id), None)
    assert row is not None, "过期 lease 的 in_progress 任务未返回恢复结果"
    assert row["republished"] is True
    assert row["new_status"] == "todo"
    assert row["recovery_error"] is None
    assert row["timeout_seconds"] == 60
    assert row["elapsed_seconds"] > 60

    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried is not None, "恢复后通过服务查询不到任务"
    assert queried.status == TaskStatus.TODO
    assert queried.remarks and "Timeout recovery after" in queried.remarks
    timeout_recovery = queried.metadata["timeout_recovery"]
    assert timeout_recovery["timed_out"] is True
    assert timeout_recovery["previous_status"] == "in_progress"
    assert timeout_recovery["recovery_source"] == "check_timeout_and_republish_tasks"
    assert timeout_recovery["timeout_seconds"] == 60
    assert timeout_recovery["elapsed_seconds"] > 60
    assert queried.metadata["lease"]["status"] == "expired"
    assert queried.metadata["lease"]["owner"] == "ci-timeout-test"
    assert queried.metadata["lease"]["timeout_seconds"] == 60

    raw = real_ci_runtime.task_service._task_dao.get_task(task.task_id)
    assert raw is not None, "恢复后 DAO 查询不到任务"
    assert raw["status"] == "todo"
    assert raw["metadata"]["timeout_recovery"]["timed_out"] is True
    assert raw["metadata"]["lease"]["status"] == "expired"
    assert raw["last_error"] is None
