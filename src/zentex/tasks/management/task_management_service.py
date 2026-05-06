from __future__ import annotations
import logging
import os
from typing import Any, Dict, Optional

from zentex.tasks.models import (
    CoordinationMode,
    SuspendedTask,
    TaskContract,
    TaskPriority,
    TaskStatus,
    TaskType,
    ZentexTask,
)
from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.models.errors import TaskStateError
from zentex.tasks.registry import TaskRegistry
from zentex.common.state import SharedStateStore
from zentex.common.coordination import LeaderElection
from zentex.tasks.management.negotiation import NegotiationGenerator
from zentex.tasks.core.llm_decomposer import LLMTaskDecomposerPlugin
from zentex.tasks.decomposition.pydantic_ai_decomposer import PydanticAITaskDecomposerPlugin
from zentex.tasks.plugins.plugin_contract_tools import (
    task_plugin_check_constraints,
    task_plugin_extract_evidence,
    task_plugin_match_capabilities,
    task_plugin_normalize_result,
    task_plugin_plan_compensation,
    task_plugin_rule_based_verification,
)
from zentex.tasks.management.persistence_mixin import TaskServicePersistenceMixin
from zentex.tasks.management.creation_mixin import TaskServiceCreationMixin
from zentex.tasks.management.q9_decomposition_mixin import TaskServiceQ9DecompositionMixin
from zentex.tasks.management.lifecycle_mixin import TaskServiceLifecycleMixin
from zentex.tasks.management.outcome_verification_mixin import TaskServiceOutcomeVerificationMixin
from zentex.tasks.management.diagnostics_mixin import TaskServiceDiagnosticsMixin
from zentex.tasks.scheduling.loop_scheduler import TaskAutoLoopScheduler
from zentex.tasks.schema import ensure_task_database_schema
from zentex.common.storage_paths import get_storage_paths
from zentex.tasks.execution.dispatch_manager import TaskDispatchManager

# Database support
try:
    from zentex.tasks.dao import (
        TaskDAO,
        SuspendedTaskDAO,
        TaskAuditLogDAO,
        TaskOutcomeDAO,
        InterventionReceiptDAO,
        IdempotencyLogDAO,
    )
    from zentex.common.database import DatabaseConnection, LRUCache
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    TaskDAO = None
    SuspendedTaskDAO = None
    TaskAuditLogDAO = None
    TaskOutcomeDAO = None
    InterventionReceiptDAO = None
    IdempotencyLogDAO = None
    DatabaseConnection = None
    LRUCache = None

# Import verification components
try:
    from zentex.tasks.verification.engine import VerificationEngine
    from zentex.tasks.verification.registry import VerifierRegistry
    from zentex.tasks.verification.models import VerificationResult as VerificationResultModel
    VERIFICATION_AVAILABLE = True
except ImportError:
    VERIFICATION_AVAILABLE = False
    VerificationEngine = None
    VerifierRegistry = None
    VerificationResultModel = None

logger = logging.getLogger("zentex.tasks.management.task_management_service")


def _task_shared_cache_ttl_seconds() -> int:
    raw = os.environ.get("ZENTEX_TASK_SHARED_CACHE_TTL_SECONDS", "86400")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        logger.warning("Invalid ZENTEX_TASK_SHARED_CACHE_TTL_SECONDS=%r; using 86400", raw)
        return 86400
    return max(value, 1)

class TaskManagementService(
    TaskServicePersistenceMixin,
    TaskServiceCreationMixin,
    TaskServiceQ9DecompositionMixin,
    TaskServiceLifecycleMixin,
    TaskServiceOutcomeVerificationMixin,
    TaskServiceDiagnosticsMixin,
):
    """
    Standalone task lifecycle manager.
    Handles registration, state流转, and persistence across brain runs.
    """
    def __init__(
        self,
        registry: TaskRegistry,
        transcript_store: Any,
        decomposer: Optional[TaskDecomposerPlugin] = None,
        *,
        allow_rule_based_test_stub: bool = False,
        auto_save: bool = True,
        use_database: bool = True,
        db_path: Optional[str] = None,
    ) -> None:
        self.registry = registry
        self.transcript_store = self._resolve_transcript_store(transcript_store)
        self.persistence = None
        self.auto_save = auto_save
        self.use_database = use_database and DATABASE_AVAILABLE

        if not self.use_database:
            raise RuntimeError("TaskManagementService requires the database layer")
        resolved_db_path = db_path or str(get_storage_paths().core_db)
        self._db = DatabaseConnection(resolved_db_path)
        ensure_task_database_schema(self._db)
        self._cache = LRUCache(max_size=1000, ttl_seconds=60)
        self._task_dao = TaskDAO(self._db, self._cache)
        self._suspended_dao = SuspendedTaskDAO(self._db, self._cache)
        self._audit_dao = TaskAuditLogDAO(self._db)
        self._outcome_dao = TaskOutcomeDAO(self._db, self._cache)
        self._intervention_dao = InterventionReceiptDAO(self._db)
        self._idempotency_dao = IdempotencyLogDAO(self._db, self._cache)
        logger.info(f"Task database layer initialized: {resolved_db_path}")

        # Cluster-friendly shared state pools
        shared_cache_ttl_seconds = _task_shared_cache_ttl_seconds()
        self._shared_tasks = SharedStateStore("tasks", ttl_seconds=shared_cache_ttl_seconds)
        self._shared_idempotency = SharedStateStore("tasks:idempotency", ttl_seconds=shared_cache_ttl_seconds)
        self._shared_interventions = SharedStateStore("tasks:interventions", ttl_seconds=shared_cache_ttl_seconds)
        self._shared_suspensions = SharedStateStore("tasks:suspensions", ttl_seconds=shared_cache_ttl_seconds)
        
        self._auto_resume_leader = LeaderElection("task-auto-resume", ttl_ms=10000)

        # Local cache for object references (only for this process)
        self._tasks: Dict[str, ZentexTask] = {}
        
        # Legacy compatibility attributes for persistence and idempotency checks
        self._idempotency_log: Dict[str, str] = {}
        self._intervention_receipts: Dict[str, Dict[str, Any]] = {}
        self._suspended_tasks: Dict[str, SuspendedTask] = {}
        self._reconcile_shared_task_state_with_database()
        self._memory_service = None
        self._learning_service = None
        self._reflection_service = None
        self._workflow_audit_service = None
        self._plugin_service = None
        self._cli_service = None
        self._mcp_service = None
        self._external_connector_service = None
        self._agent_service = None
        
        if decomposer is None:
            if not allow_rule_based_test_stub:
                raise RuntimeError(
                    "TaskManagementService requires an explicit mission decomposer. "
                    "Rule-based decomposer stubs must not be wired into production chains."
                )
            decomposer = TaskDecomposerPlugin()
        self.decomposer = decomposer
        
        # Initialize Negotiation Engine
        self.negotiation_generator = NegotiationGenerator(self)
        
        # Initialize Verification Engine (if available)
        self._verification_engine = None
        self._verifier_registry = None
        if VERIFICATION_AVAILABLE:
            try:
                self._verifier_registry = VerifierRegistry()
                self._verification_engine = VerificationEngine(self._verifier_registry)
                logger.info("Verification engine initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize verification engine: {e}")

        # Initialize the Action Heartbeat controller
        # We don't pass the registry here because TaskDispatchManager expects a PluginLayer,
        # not a TaskRegistry. The actual PluginService will be attached later via attach_dependencies.
        self._dispatch_manager = TaskDispatchManager(
            plugin_layer=None,
            transcript_store=self.transcript_store,
            task_service=self,
        )

async def recover_waiting_confirmation_task(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    from zentex.tasks.execution.workflow_sync import recover_waiting_confirmation_task as _impl

    return await _impl(*args, **kwargs)


def verify_writeback_content(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    from zentex.tasks.verification.writebacks import verify_writeback_content as _impl

    return _impl(*args, **kwargs)


def verify_external_side_effect(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    from zentex.tasks.verification.external_evidence import verify_external_side_effect as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "TaskManagementService",
    "TaskRegistry",
    "TaskStatus",
    "TaskType",
    "TaskContract",
    "CoordinationMode",
    "TaskPriority",
    "SuspendedTask",
    "ZentexTask",
    "TaskStateError",
    "LLMTaskDecomposerPlugin",
    "PydanticAITaskDecomposerPlugin",
    "TaskAutoLoopScheduler",
    "task_plugin_normalize_result",
    "task_plugin_extract_evidence",
    "task_plugin_rule_based_verification",
    "task_plugin_match_capabilities",
    "task_plugin_check_constraints",
    "task_plugin_plan_compensation",
    "recover_waiting_confirmation_task",
    "verify_writeback_content",
    "verify_external_side_effect",
]


# Global singleton instance for tasks service
_default_service: Optional[TaskManagementService] = None


def get_service() -> TaskManagementService:
    """Standard service factory function for launcher assembly.
    
    Returns the global TaskManagementService instance, creating it if necessary.
    This function is required by the SystemAssembler to initialize the tasks service.
    
    Note: This creates a minimal instance with default decomposer for startup.
    The service will be properly reconfigured by the kernel with actual dependencies.
    """
    global _default_service
    if _default_service is None:
        from zentex.tasks.registry import TaskRegistry
        from zentex.tasks.core.decomposer import TaskDecomposerPlugin
        _default_service = TaskManagementService(
            registry=TaskRegistry(),
            transcript_store=None,  # Will be set by kernel
            decomposer=TaskDecomposerPlugin(),
        )
    return _default_service
