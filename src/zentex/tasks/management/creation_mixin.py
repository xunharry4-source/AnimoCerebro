from __future__ import annotations

from zentex.tasks.management.task_creation_flow_mixin import TaskServiceCreationFlowMixin
from zentex.tasks.management.metadata_noise_mixin import TaskServiceMetadataNoiseMixin
from zentex.tasks.management.mission_decomposition_mixin import TaskServiceMissionDecompositionMixin


class TaskServiceCreationMixin(
    TaskServiceCreationFlowMixin,
    TaskServiceMetadataNoiseMixin,
    TaskServiceMissionDecompositionMixin,
):
    pass
