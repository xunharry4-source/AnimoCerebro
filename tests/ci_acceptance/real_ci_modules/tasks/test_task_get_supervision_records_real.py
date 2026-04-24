from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_supervision_records_real(real_ci_runtime) -> None:
    """功能：验证 get_supervision_records 返回列表。"""
    suffix = unique_suffix()
    task = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="supervision-rec"))
    await real_ci_runtime.task_service.intervene(
        task.task_id,
        action="resume",
        idempotency_key=f"intervene-supervision-{suffix}",
        remarks="ci",
        operator_id="ci_real_modules",
    )
    rows = real_ci_runtime.task_service.get_supervision_records(task.task_id)
    assert isinstance(rows, list)
    if real_ci_runtime.task_service.transcript_store is None:
        assert rows == []
    else:
        assert any(item.get("task_id") == task.task_id for item in rows), "监督记录中未出现目标任务"
