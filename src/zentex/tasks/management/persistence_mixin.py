from __future__ import annotations

from zentex.tasks.management.service_wiring_mixin import TaskServiceWiringMixin
from zentex.tasks.management.task_serialization_mixin import TaskServiceSerializationMixin
from zentex.tasks.management.task_query_mixin import TaskServiceQueryMixin


class TaskServicePersistenceMixin(
    TaskServiceWiringMixin,
    TaskServiceSerializationMixin,
    TaskServiceQueryMixin,
):
    pass
