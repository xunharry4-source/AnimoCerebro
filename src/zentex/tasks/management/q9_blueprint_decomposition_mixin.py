from __future__ import annotations

from zentex.tasks.management.service_context import *
from zentex.tasks.decomposition.q9_task_decomposition_service import (
    decompose_q9_blueprint_task as decompose_q9_blueprint_task_impl,
)


class TaskServiceQ9BlueprintDecompositionMixin:
    async def decompose_q9_blueprint_task(self, q9_task: ZentexTask) -> List[ZentexTask]:
        return await decompose_q9_blueprint_task_impl(self, q9_task)
