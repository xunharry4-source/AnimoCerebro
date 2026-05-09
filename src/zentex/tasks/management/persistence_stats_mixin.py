from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServicePersistenceStatsMixin:
    def save_state(self) -> bool:
        return True

    def get_persistence_stats(self) -> Optional[Dict[str, Any]]:
        return None


