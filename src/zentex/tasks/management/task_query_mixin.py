from __future__ import annotations

from zentex.tasks.management.task_list_query_mixin import TaskServiceListQueryMixin
from zentex.tasks.management.task_group_query_mixin import TaskServiceGroupQueryMixin
from zentex.tasks.management.task_lookup_seed_mixin import TaskServiceLookupSeedMixin


class TaskServiceQueryMixin(
    TaskServiceListQueryMixin,
    TaskServiceGroupQueryMixin,
    TaskServiceLookupSeedMixin,
):
    pass
