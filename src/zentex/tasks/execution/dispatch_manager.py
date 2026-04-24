import logging
from typing import Any, Dict, List, Optional

from zentex.tasks.dispatch.router_impl import UnifiedTaskRouter
from zentex.tasks.dispatch.internal import InternalPluginExecutor
from zentex.tasks.execution.worker import TaskExecutionWorker, WorkerConfig
from zentex.common.state import SharedStateStore

logger = logging.getLogger(__name__)

class TaskDispatchManager:
    """
    The 'Action Posture Controller' for Zentex.
    Bridges Q9 Cognitive Posture to Physical Task Dispatching.
    
    Implements 'Option A': Sequential execution with safety locks.
    """

    def __init__(self, plugin_layer: Any = None, transcript_store: Any = None):
        # Initialize the physical execution stack
        self._executor = InternalPluginExecutor(plugin_layer)
        self._router = UnifiedTaskRouter(
            internal_executor=self._executor, 
            transcript_store=transcript_store
        )
        
        # Load posture from shared state
        self._posture_store = SharedStateStore("q9_posture")

    def set_plugin_layer(self, plugin_layer: Any) -> None:
        """Propagate the plugin layer reference to the underlying executor."""
        self._executor.set_plugin_layer(plugin_layer)
        
    def get_worker(self, task_dao: Any) -> TaskExecutionWorker:
        """Instantiate a worker with current cognitive constraints."""
        posture = self._get_current_posture()
        is_conservative = posture.get("conservative_mode_triggered", False)
        rhythm = posture.get("action_rhythm_hint", "steady_incremental")
        
        # Adjust worker config based on Q9 posture
        config = WorkerConfig(
            batch_size=1 if is_conservative or rhythm == "confirm_before_commit" else 5,
            max_attempts=3,
        )
        
        return TaskExecutionWorker(
            task_dao=task_dao,
            router=self._router,
            internal_executor=self._executor,
            config=config
        )

    def _get_current_posture(self) -> Dict[str, Any]:
        """Fetch the latest Q9 posture from the brain's shared state."""
        try:
            # We look for the most recent session's posture
             # In a real environment, we'd pass the session_id here.
             # For now, we take a global 'current_posture' fallback.
            data = self._posture_store.get("current_posture") or {}
            return data
        except Exception:
            return {}

    async def run_cycle(self, task_dao: Any):
        """Perform one execution cycle under cognitive supervision."""
        worker = self.get_worker(task_dao)
        stats = await worker.run_cycle()
        return stats
