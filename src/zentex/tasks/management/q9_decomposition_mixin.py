from __future__ import annotations

from zentex.tasks.management.assignment_gate_mixin import TaskServiceAssignmentGateMixin
from zentex.tasks.management.q9_blueprint_decomposition_mixin import TaskServiceQ9BlueprintDecompositionMixin


class TaskServiceQ9DecompositionMixin(
    TaskServiceAssignmentGateMixin,
    TaskServiceQ9BlueprintDecompositionMixin,
):
    pass
