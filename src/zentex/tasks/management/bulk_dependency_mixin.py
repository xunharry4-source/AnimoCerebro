from __future__ import annotations

from zentex.tasks.management.bulk_operation_mixin import TaskServiceBulkOperationMixin
from zentex.tasks.management.dependency_graph_mixin import TaskServiceDependencyGraphMixin
from zentex.tasks.management.persistence_stats_mixin import TaskServicePersistenceStatsMixin


class TaskServiceBulkDependencyMixin(
    TaskServiceBulkOperationMixin,
    TaskServiceDependencyGraphMixin,
    TaskServicePersistenceStatsMixin,
):
    pass
