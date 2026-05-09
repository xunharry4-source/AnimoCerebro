from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_list_tasks_real(real_ci_runtime) -> None:
    """功能：验证 list_tasks 在库里过滤并分页返回业务结果。"""
    suffix = unique_suffix()
    source_module = f"ci_list_page_{suffix}"
    created = []
    try:
        for idx in range(3):
            created.append(
                await real_ci_runtime.task_service.create_task(
                    task_payload(
                        suffix=f"{suffix}-{idx}",
                        title_prefix="list",
                        source_module=source_module,
                    )
                )
            )

        first_page = real_ci_runtime.task_service.list_tasks(
            source_module=source_module,
            limit=2,
            offset=0,
        )
        assert len(first_page) == 2
        assert all(item.metadata["source_module"] == source_module for item in first_page)
        assert all(item.status.value == "todo" for item in first_page)

        second_page = real_ci_runtime.task_service.list_tasks(
            source_module=source_module,
            limit=2,
            offset=2,
        )
        assert len(second_page) == 1
        assert second_page[0].metadata["source_module"] == source_module
        returned_ids = {item.task_id for item in first_page + second_page}
        assert returned_ids == {item.task_id for item in created}
    finally:
        if created:
            real_ci_runtime.task_service.bulk_delete([item.task_id for item in created], force=True)
