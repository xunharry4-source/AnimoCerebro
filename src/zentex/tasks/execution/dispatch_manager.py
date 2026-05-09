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

    def __init__(
        self,
        plugin_layer: Any = None,
        transcript_store: Any = None,
        task_service: Any = None,
        cli_service: Any = None,
        mcp_service: Any = None,
        external_connector_service: Any = None,
        agent_service: Any = None,
    ):
        # Initialize the physical execution stack
        self._executor = InternalPluginExecutor(plugin_layer)
        self._router = UnifiedTaskRouter(
            internal_executor=self._executor, 
            transcript_store=transcript_store
        )
        self._task_service = task_service
        self._cli_service = cli_service
        self._mcp_service = mcp_service
        self._external_connector_service = external_connector_service
        self._agent_service = agent_service
        
        # Load posture from shared state
        self._posture_store = SharedStateStore("q9_posture")

    def set_plugin_layer(self, plugin_layer: Any) -> None:
        """Propagate the plugin layer reference to the underlying executor."""
        self._executor.set_plugin_layer(plugin_layer)

    def attach_external_services(
        self,
        *,
        task_service: Any = None,
        cli_service: Any = None,
        mcp_service: Any = None,
        external_connector_service: Any = None,
        agent_service: Any = None,
    ) -> None:
        if task_service is not None:
            self._task_service = task_service
        if cli_service is not None:
            self._cli_service = cli_service
        if mcp_service is not None:
            self._mcp_service = mcp_service
        if external_connector_service is not None:
            self._external_connector_service = external_connector_service
        if agent_service is not None:
            self._agent_service = agent_service
        
    def get_worker(self, task_dao: Any) -> TaskExecutionWorker:
        """Instantiate a worker with current cognitive constraints."""
        posture = self._get_current_posture()
        is_conservative = posture.get("conservative_mode_triggered", False)
        rhythm = posture.get("action_rhythm_hint", "steady_incremental")
        requires_confirmation = bool(
            posture.get("approval_gate")
            or posture.get("operator_approval_required")
            or rhythm == "confirm_before_commit"
        )
        
        # Adjust worker config based on Q9 posture
        config = WorkerConfig(
            batch_size=1 if is_conservative or rhythm == "confirm_before_commit" else 5,
            max_attempts=3,
            require_approval=requires_confirmation,
            conservative_mode=bool(is_conservative),
        )
        
        return TaskExecutionWorker(
            task_dao=task_dao,
            router=self._router,
            internal_executor=self._executor,
            task_service=self._task_service,
            cli_service=self._cli_service,
            mcp_service=self._mcp_service,
            external_connector_service=self._external_connector_service,
            agent_service=self._agent_service,
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
