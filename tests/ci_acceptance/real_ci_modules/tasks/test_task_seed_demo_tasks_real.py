from __future__ import annotations

import pytest

from zentex.tasks.models import TaskStatus, TaskType
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


@pytest.mark.asyncio
async def test_task_seed_demo_tasks_real(real_ci_runtime) -> None:
    """功能：验证 seed_demo_tasks 批量注入。"""
    suffix = unique_suffix()
    seeded = await real_ci_runtime.task_service.seed_demo_tasks([
        {
            "idempotency_key": f"seed-{suffix}",
            "title": f"seed-{suffix}",
            "task_type": TaskType.SYSTEM_ACTION,
            "status": TaskStatus.TODO,
            "originator_id": "ci",
            "remarks": "seed",
        }
    ])
    assert len(seeded) == 1
