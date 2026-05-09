from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from zentex.tasks.models import TaskContract, TaskType

logger = logging.getLogger(__name__)


class TaskRegistry:
    """
    Registry for task types and their corresponding handlers and behaviors.
    """

    def __init__(self) -> None:
        self._registry: Dict[TaskType, Dict[str, Any]] = {}

    def register_handler(self, task_type: TaskType, handler: Callable, contract: TaskContract):
        self._registry[task_type] = {
            "handler": handler,
            "contract": contract,
        }
        logger.info(
            "Registered Task Handler: %s (serial_only=%s)",
            task_type,
            contract.serial_only,
        )

    def get_handler(self, task_type: TaskType) -> Optional[Callable]:
        return self._registry.get(task_type, {}).get("handler")

    def get_contract(self, task_type: TaskType) -> Optional[TaskContract]:
        return self._registry.get(task_type, {}).get("contract")

