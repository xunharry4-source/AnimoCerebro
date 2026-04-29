from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_list_tasks_grouped_real(real_ci_runtime) -> None:
    """功能：验证 list_tasks_grouped 在库里按 source_module 分组分页。"""
    suffix = unique_suffix()
    source_module = f"ci_group_page_{suffix}"
    created = []
    try:
        for idx in range(2):
            created.append(
                await real_ci_runtime.task_service.create_task(
                    task_payload(
                        suffix=f"{suffix}-{idx}",
                        title_prefix="group",
                        source_module=source_module,
                    )
                )
            )
        other = await real_ci_runtime.task_service.create_task(
            task_payload(
                suffix=f"{suffix}-other",
                title_prefix="group",
                source_module=f"{source_module}_other",
            )
        )
        created.append(other)

        grouped = real_ci_runtime.task_service.list_tasks_grouped(
            source_module=source_module,
            limit_per_group=1,
            offset=0,
        )
        assert set(grouped.keys()) == {"in_progress", "pending", "waiting_confirmation", "completed", "cancelled"}
        assert len(grouped["pending"]) == 1
        assert grouped["pending"][0].metadata["source_module"] == source_module
        assert grouped["pending"][0].status.value == "todo"
        assert grouped["in_progress"] == []
        assert grouped["completed"] == []
    finally:
        if created:
            real_ci_runtime.task_service.bulk_delete([item.task_id for item in created], force=True)
