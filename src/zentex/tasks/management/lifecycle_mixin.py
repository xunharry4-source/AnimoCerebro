from __future__ import annotations

from zentex.tasks.management.status_control_mixin import TaskServiceStatusControlMixin
from zentex.tasks.management.suspension_mixin import TaskServiceSuspensionMixin
from zentex.tasks.management.worker_timeout_mixin import TaskServiceWorkerTimeoutMixin
from zentex.tasks.management.bulk_dependency_mixin import TaskServiceBulkDependencyMixin


class TaskServiceLifecycleMixin(
    TaskServiceStatusControlMixin,
    TaskServiceSuspensionMixin,
    TaskServiceWorkerTimeoutMixin,
    TaskServiceBulkDependencyMixin,
):
    pass
