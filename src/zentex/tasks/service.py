from __future__ import annotations
import asyncio
import copy
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

from zentex.tasks.models import ZentexTask, TaskStatus, TaskType, TaskContract, CoordinationMode, TaskPriority, SuspendedTask
from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.models.errors import TaskStateError
from zentex.tasks.registry import TaskRegistry
from zentex.kernel import AuditEventType
from zentex.common.state import SharedStateStore
from zentex.common.locking import get_lock_for_resource
from zentex.common.coordination import LeaderElection
from zentex.tasks.management.negotiation import NegotiationGenerator
from zentex.tasks.core.llm_decomposer import LLMTaskDecomposerPlugin
from zentex.tasks.scheduling.loop_scheduler import TaskAutoLoopScheduler
from zentex.tasks.schema import ensure_task_database_schema
from zentex.common.storage_paths import get_storage_paths
from zentex.tasks.execution.dispatch_manager import TaskDispatchManager
from zentex.kernel.state_domain.transcript import NullTranscriptStore, TranscriptStore
from zentex.tasks import outcomes as task_outcomes
from zentex.tasks.verification.status_bridge import maybe_route_done_status_update_through_verification
from zentex.tasks.lifecycle_diagnostics import (
    build_task_fault_injection_report,
    build_task_lifecycle_diagnostic_report,
)
from zentex.tasks.timeout_recovery import build_timeout_recovery_action

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

logger = logging.getLogger(__name__)

class TaskManagementService:
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
        self._shared_tasks = SharedStateStore("tasks")
        self._shared_idempotency = SharedStateStore("tasks:idempotency")
        self._shared_interventions = SharedStateStore("tasks:interventions")
        self._shared_suspensions = SharedStateStore("tasks:suspensions")
        
        self._auto_resume_leader = LeaderElection("task-auto-resume", ttl_ms=10000)

        # Local cache for object references (only for this process)
        self._tasks: Dict[str, ZentexTask] = {}
        
        # Legacy compatibility attributes for persistence and idempotency checks
        self._idempotency_log: Dict[str, str] = {}
        self._intervention_receipts: Dict[str, Dict[str, Any]] = {}
        self._suspended_tasks: Dict[str, SuspendedTask] = {}
        
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
        self._dispatch_manager = TaskDispatchManager(plugin_layer=None, transcript_store=self.transcript_store)

    def close(self) -> None:
        close = getattr(self._db, "close", None)
        if callable(close):
            close()

    def attach_dependencies(
        self,
        *,
        plugin_service: Any = None,
        transcript_store: Any = None,
    ) -> None:
        """
        Inject external service references into the task management stack.
        This resolves the circular dependency between tasks and plugins.
        """
        if plugin_service is not None:
            self._dispatch_manager.set_plugin_layer(plugin_service)
            logger.info("TaskManagementService: PluginService attached to dispatcher.")
        
        if transcript_store is not None:
            # Update transcript store if it was missing during init
            resolved_store = self._resolve_transcript_store(transcript_store)
            self.transcript_store = resolved_store
            self._transcript_store = resolved_store
            # UnifiedTaskRouter also needs a transcript store
            if hasattr(self._dispatch_manager, "_router"):
                self._dispatch_manager._router.transcript_store = resolved_store

    def _resolve_transcript_store(self, transcript_store: Any) -> Any:
        if transcript_store is None:
            return None
        if isinstance(transcript_store, NullTranscriptStore):
            logger.warning(
                "TaskManagementService received NullTranscriptStore; creating a local TranscriptStore fallback for task audits"
            )
            return TranscriptStore(session_id="task-management-runtime")
        return transcript_store

    def _task_to_dict(self, task: ZentexTask) -> Dict[str, Any]:
        """Convert ZentexTask to dictionary for database storage."""
        return {
            'task_id': task.task_id,
            'parent_task_id': task.parent_task_id,
            'subtask_ids': task.subtask_ids,
            'depends_on': task.depends_on,
            'bundle_id': task.bundle_id,
            'subtask_id': task.subtask_id,
            'idempotency_key': task.idempotency_key,
            'title': task.title,
            'task_type': task.task_type.value,
            'status': task.status.value,
            'priority': task.priority.value,
            'progress': task.progress,
            'originator_id': task.originator_id,
            'target_id': task.target_id,
            'remarks': task.remarks,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'estimated_duration': task.estimated_duration,
            'tags': task.tags,
            'contract': task.contract.model_dump() if hasattr(task.contract, 'model_dump') else dict(task.contract.__dict__),
            'metadata': task.metadata,
            'last_updated_at': task.last_updated_at.isoformat(),
            'created_at': task.created_at.isoformat(),
        }

    def _dict_to_task(self, data: Dict[str, Any]) -> ZentexTask:
        """Convert database dictionary to ZentexTask."""
        # Convert string enums back to enum types
        if 'task_type' in data and isinstance(data['task_type'], str):
            data['task_type'] = TaskType(data['task_type'])
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = TaskStatus(data['status'])
        if 'priority' in data and isinstance(data['priority'], str):
            data['priority'] = TaskPriority(data['priority'])
        
        # Convert ISO format strings back to datetime
        for field in ['started_at', 'completed_at', 'deadline', 'last_updated_at', 'created_at']:
            if field in data and data[field] and isinstance(data[field], str):
                try:
                    data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    data[field] = None
        
        # Ensure collection fields are never None (Pydantic v2 requirement)
        # This prevents ValidationErrors when database columns contain NULL for these fields.
        for list_field in ['subtask_ids', 'depends_on', 'tags']:
            if data.get(list_field) is None:
                data[list_field] = []
        
        # Handle contract and metadata
        if data.get('contract') is None:
            data['contract'] = {}
        if data.get('metadata') is None:
            data['metadata'] = {}

        if 'contract' in data and isinstance(data['contract'], dict):
            data['contract'] = TaskContract(**data['contract'])
        
        return ZentexTask(**data)

    def _sync_task_to_database(self, task: ZentexTask) -> bool:
        """Sync a task to database if database is enabled."""
        if not self.use_database or not self._task_dao:
            return False
        
        try:
            task_data = self._task_to_dict(task)
            return self._task_dao.create_task(task_data) if not self._task_dao.get_task(task.task_id) else self._task_dao.update_task(task.task_id, task_data)
        except Exception as e:
            logger.error(f"Failed to sync task to database: {e}")
            return False

    def _load_task_from_database(self, task_id: str) -> Optional[ZentexTask]:
        """Load a task from database if database is enabled."""
        if not self.use_database or not self._task_dao:
            return None
        
        try:
            data = self._task_dao.get_task(task_id)
            if data:
                return self._dict_to_task(data)
        except Exception as e:
            logger.error(f"Failed to load task from database: {e}")
        return None

    def list_tasks(self,
                 status: Optional[TaskStatus] = None,
                 priority: Optional[TaskPriority] = None,
                 tags: Optional[List[str]] = None,
                 parent_task_id: Optional[str] = None,
                 task_type: Optional[TaskType] = None,
                 originator_id: Optional[str] = None,
                 target_id: Optional[str] = None,
                 overdue_only: bool = False,
                 source_module: Optional[str] = None,
                 metadata_filters: Optional[Dict[str, Any]] = None,
                 limit: int = 100,
                 offset: int = 0) -> List[ZentexTask]:
        """List tasks with database-backed filtering and pagination."""
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")
        capped_limit = max(1, min(int(limit), 500))
        normalized_offset = max(0, int(offset))
        db_tasks = self._task_dao.list_tasks(
            status=status.value if status else None,
            priority=priority.value if priority else None,
            task_type=task_type.value if task_type else None,
            parent_task_id=parent_task_id,
            originator_id=originator_id,
            target_id=target_id,
            source_module=source_module,
            metadata_filters=metadata_filters,
            tags=tags,
            overdue_only=overdue_only,
            limit=capped_limit,
            offset=normalized_offset,
        )
        return [self._dict_to_task(item) for item in db_tasks]

    def count_tasks(self,
                    status: Optional[TaskStatus] = None,
                    priority: Optional[TaskPriority] = None,
                    tags: Optional[List[str]] = None,
                    parent_task_id: Optional[str] = None,
                    task_type: Optional[TaskType] = None,
                    originator_id: Optional[str] = None,
                    target_id: Optional[str] = None,
                    overdue_only: bool = False,
                    source_module: Optional[str] = None,
                    metadata_filters: Optional[Dict[str, Any]] = None) -> int:
        """Count tasks using the same database-backed filters as list_tasks."""
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")
        return self._task_dao.count_tasks(
            status=status.value if status else None,
            priority=priority.value if priority else None,
            task_type=task_type.value if task_type else None,
            parent_task_id=parent_task_id,
            originator_id=originator_id,
            target_id=target_id,
            source_module=source_module,
            metadata_filters=metadata_filters,
            tags=tags,
            overdue_only=overdue_only,
        )

    def list_tasks_grouped(
        self,
        *,
        source_module: Optional[str] = None,
        limit_per_group: int = 100,
        offset: int = 0,
    ) -> Dict[str, List[ZentexTask]]:
        """Return tasks partitioned into presentation groups.

        Business rule: which statuses belong to each group is a domain
        decision and must not leak into web_console routers.
        """
        capped_limit = max(1, min(int(limit_per_group), 500))
        normalized_offset = max(0, int(offset))
        return {
            "in_progress": self.list_tasks(
                status=TaskStatus.IN_PROGRESS,
                source_module=source_module,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "pending": (
                self.list_tasks(
                    status=TaskStatus.TODO,
                    source_module=source_module,
                    limit=capped_limit,
                    offset=normalized_offset,
                )
                + self.list_tasks(
                    status=TaskStatus.BLOCKED,
                    source_module=source_module,
                    limit=capped_limit,
                    offset=normalized_offset,
                )
            )[:capped_limit],
            "waiting_confirmation": self.list_tasks(
                status=TaskStatus.WAITING_CONFIRMATION,
                source_module=source_module,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "completed": self.list_tasks(
                status=TaskStatus.DONE,
                source_module=source_module,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "cancelled": (
                self.list_tasks(
                    status=TaskStatus.FAILED,
                    source_module=source_module,
                    limit=capped_limit,
                    offset=normalized_offset,
                )
                + self.list_tasks(
                    status=TaskStatus.SUSPENDED,
                    source_module=source_module,
                    limit=capped_limit,
                    offset=normalized_offset,
                )
                + self.list_tasks(
                    status=TaskStatus.ARCHIVED,
                    source_module=source_module,
                    limit=capped_limit,
                    offset=normalized_offset,
                )
            )[:capped_limit],
        }

    @property
    def revision(self) -> int:
        """Monotonically increasing counter; 0 when the service has no tracker.

        Callers (e.g. WebSocket stream) use this to detect in-flight changes
        without accessing private attributes.
        """
        return getattr(self, "_revision", 0)

    def get_task(self, task_id: str) -> Optional[ZentexTask]:
        """Get a task by ID.
        
        G15: Truth Consolidation.
        Priority: Database (if enabled) > Shared Memory > Local Cache.
        """
        if not task_id:
            return None

        task = self._load_task_from_database(task_id)
        if task:
            self._tasks[task_id] = task
            self._shared_tasks.set(task_id, task)
            return task
        return None

    async def seed_demo_tasks(self, tasks: List[Dict[str, Any]]) -> List[ZentexTask]:
        """Seed local demo tasks through the service boundary."""
        seeded: List[ZentexTask] = []
        for payload in tasks:
            key = str(payload["idempotency_key"])
            existing_id = self._shared_idempotency.get(key)
            if existing_id:
                existing_task = self.get_task(existing_id)
                if existing_task is not None:
                    seeded.append(existing_task)
                continue

            now = datetime.now(timezone.utc)
            status = payload["status"]
            if isinstance(status, str):
                status = TaskStatus(status)
            task_type = payload["task_type"]
            if isinstance(task_type, str):
                task_type = TaskType(task_type)

            started_at = None
            completed_at = None
            if status == TaskStatus.IN_PROGRESS:
                started_at = now
            elif status == TaskStatus.DONE:
                started_at = now
                completed_at = now

            task = ZentexTask(
                task_id=str(uuid4())[:8],
                idempotency_key=key,
                title=str(payload["title"]),
                task_type=task_type,
                status=status,
                progress=float(payload.get("progress", 0.0)),
                originator_id=str(payload["originator_id"]),
                target_id=str(payload.get("target_id")) if payload.get("target_id") is not None else None,
                remarks=str(payload["remarks"]) if payload.get("remarks") is not None else None,
                started_at=started_at,
                completed_at=completed_at,
                created_at=now,
                last_updated_at=now,
            )

            self._shared_tasks.set(task.task_id, task)
            self._shared_idempotency.set(key, task.task_id)
            self._tasks[task.task_id] = task
            self._idempotency_log[key] = task.task_id
            seeded.append(task)

        return seeded

    async def create_task(self, payload: Dict[str, Any]) -> ZentexTask:
        """Create a new task with database persistence."""
        # Check idempotency (Shared)
        key = payload.get("idempotency_key")
        if key:
            # Check database first if enabled
            if self.use_database and self._idempotency_dao:
                existing_task_id = self._idempotency_dao.check_idempotency(key)
                if existing_task_id:
                    logger.warning(f"Duplicate task submission with idempotency_key: {key}")
                    existing_task = self.get_task(existing_task_id)
                    if existing_task:
                        return existing_task
            
            # Fallback to shared state
            existing_id = self._shared_idempotency.get(key)
            if existing_id:
                logger.warning(f"Duplicate task submission with idempotency_key: {key}")
                existing_task = self.get_task(existing_id)
                if existing_task is not None:
                    return existing_task

        # Distributed lock to prevent race during creation
        lock_id = key if key else f"new-task-{uuid4()}"
        with get_lock_for_resource(f"task-create:{lock_id}"):
            # Re-check idempotency inside lock
            if key:
                if self.use_database and self._idempotency_dao:
                    existing_task_id = self._idempotency_dao.check_idempotency(key)
                    if existing_task_id:
                        return self.get_task(existing_task_id)
                
                existing_id = self._shared_idempotency.get(key)
                if existing_id:
                    return self.get_task(existing_id)

            task_id = str(uuid4())[:8]
            task = ZentexTask(
                task_id=task_id,
                **payload
            )
            
            # Save to shared state
            self._shared_tasks.set(task_id, task)
            self._tasks[task_id] = task
            
            # Save to database if enabled
            if not self._sync_task_to_database(task):
                self._shared_tasks.delete(task_id)
                self._tasks.pop(task_id, None)
                raise TaskStateError(f"Failed to persist task {task_id} to database")
            if key and self._idempotency_dao:
                self._idempotency_dao.record_idempotency(key, task_id)
            
            # Legacy: save to shared idempotency
            if key:
                self._shared_idempotency.set(key, task_id)
                
            # Record audit
            self._record_audit(task_id, "TASK_CREATED", {"payload": payload})
            
            # Auto-decompose missions
            if task.task_type == TaskType.MISSION:
                asyncio.create_task(self.decompose_and_dispatch_mission(task))
                
            return task

    async def update_task_metadata(
        self,
        task_id: str,
        metadata_updates: Dict[str, Any],
        *,
        remarks: Optional[str] = None,
    ) -> ZentexTask:
        """Merge metadata into a task and persist the change."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        task.metadata = {**task.metadata, **metadata_updates}
        task.last_updated_at = datetime.now(timezone.utc)
        if remarks:
            task.remarks = remarks

        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task

        if self.use_database:
            if not self._sync_task_to_database(task):
                raise TaskStateError(f"Failed to persist metadata updates for task {task_id}")
            if self._audit_dao:
                self._audit_dao.log_action(
                    task_id=task_id,
                    action="TASK_METADATA_UPDATED",
                    operator_id="system",
                    old_status=task.status.value,
                    new_status=task.status.value,
                    details={"metadata_updates": metadata_updates, "remarks": remarks},
                )

        self._record_audit(
            task_id,
            "TASK_METADATA_UPDATED",
            {"metadata_updates": metadata_updates, "remarks": remarks},
        )
        # Read-after-write guard: metadata mutation must be query-visible.
        refreshed = self._load_task_from_database(task_id)
        if refreshed is None or any(
            refreshed.metadata.get(key) != value for key, value in metadata_updates.items()
        ):
            raise TaskStateError(f"Metadata read-after-write mismatch for task {task_id}")
        return task

    async def decompose_and_dispatch_mission(self, mission_task: ZentexTask):
        """
        Step 2 & 3: Mission Decomposition & Dispatch.
        """
        subtask_data = self.decomposer.decompose_mission(mission_task.title, mission_task.remarks or "")
        
        logger.info(f"Dispatching {len(subtask_data)} subtasks for mission {mission_task.task_id}")
        
        local_id_map: Dict[str, str] = {} # local step id -> physical task_id

        # Pass 1: Creation
        for item in subtask_data:
            local_id = item.pop("local_id")
            item["parent_task_id"] = mission_task.task_id
            item["originator_id"] = mission_task.originator_id
            item["idempotency_key"] = f"sub-{mission_task.task_id}-{local_id}"
            
            # Subtask contract enforcement
            contract = TaskContract(
                coordination_mode=item.get("coordination_mode", CoordinationMode.PARALLEL),
                # If step-1 fails, mission fails (halt)
                failure_strategy="halt" if "step-1" in local_id else "retry_all"
            )
            
            st = await self.create_task({**item, "contract": contract})
            local_id_map[local_id] = st.task_id
            mission_task.subtask_ids.append(st.task_id)

        # Pass 2: Dependency Linkage
        for item, st_id in zip(subtask_data, mission_task.subtask_ids):
            st = self._tasks[st_id]
            st.depends_on = [local_id_map[dep] for dep in item.get("depends_on", []) if dep in local_id_map]
            self._shared_tasks.set(st_id, st)
            self._tasks[st_id] = st
            if self.use_database and not self._sync_task_to_database(st):
                raise TaskStateError(f"Failed to persist dependency linkage for subtask {st_id}")

        mission_task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(mission_task.task_id, mission_task)
        self._tasks[mission_task.task_id] = mission_task
        if self.use_database and not self._sync_task_to_database(mission_task):
            raise TaskStateError(f"Failed to persist mission decomposition for task {mission_task.task_id}")

        self._record_audit(mission_task.task_id, "MISSION_DECOMPOSED", {"subtask_ids": mission_task.subtask_ids})
    async def claim_task(self, task_id: str, handler_id: str) -> ZentexTask:
        """
        Collaborative claiming of a subtask.
        """
        task = self.get_task(task_id)
        if not task:
             raise KeyError(f"Task {task_id} not found")
             
        # Check dependencies
        for dep_id in task.depends_on:
            dep_task = self.get_task(dep_id)
            if dep_task and dep_task.status != TaskStatus.DONE:
                raise TaskStateError(f"Dependency {dep_id} is not yet DONE.")

        task.target_id = handler_id
        task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if self.use_database and not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist task claim target for {task_id}")
        return await self.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks=f"Claimed by {handler_id}")

    async def heartbeat_task(self, task_id: str) -> None:
        """
        G39: Signal that a task is still active. 
        Updates last_updated_at to prevent stale reclamation.
        """
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"Heartbeat attempted for non-existent task: {task_id}")
            return

        now = datetime.now(timezone.utc)
        task.last_updated_at = now
        
        # Save to shared and local memory
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task

        # Save to database (only update the timestamp to minimize overhead)
        if self.use_database and self._task_dao:
            try:
                if not self._task_dao.update_task(task_id, {"last_updated_at": now.isoformat()}):
                    raise TaskStateError(f"Failed to persist task heartbeat for {task_id}")
            except Exception as e:
                logger.error(f"Failed to persist task heartbeat for {task_id}: {e}")
                raise

        # Record minor audit event
        self._record_audit(task_id, "TASK_HEARTBEAT", {"timestamp": now.isoformat()})

    async def update_task_status(self, task_id: str, new_status: TaskStatus, remarks: Optional[str] = None):
        """
        State Machine Redline: Validates illegal transitions.
        
        G16: Atomic status update.
        G18: Asynchronous execution.
        """
        task = self.get_task(task_id)  # Returns most current state from DB/Shared
        if not task:
            raise KeyError(f"Task {task_id} not found")

        bridged_task = await maybe_route_done_status_update_through_verification(
            self,
            task=task,
            task_id=task_id,
            new_status=new_status,
            remarks=remarks,
        )
        if bridged_task is not None:
            return bridged_task

        # Define legal transitions
        legal_from: Dict[TaskStatus, List[TaskStatus]] = {
            TaskStatus.TODO: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED],
            TaskStatus.IN_PROGRESS: [TaskStatus.TODO, TaskStatus.WAITING_CONFIRMATION, TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SUSPENDED],
            TaskStatus.BLOCKED: [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED],
            TaskStatus.WAITING_CONFIRMATION: [TaskStatus.IN_PROGRESS, TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SUSPENDED],
            TaskStatus.SUSPENDED: [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.ARCHIVED],
            TaskStatus.DONE: [TaskStatus.ARCHIVED], # Can only archive done tasks
            TaskStatus.FAILED: [TaskStatus.TODO], # Allow retry
            TaskStatus.ARCHIVED: [] # Terminal state
        }
        
        if new_status not in legal_from.get(task.status, []):
            raise TaskStateError(f"Illegal transition: {task.status} -> {new_status}")

        old_status = task.status
        
        # Update metadata and timestamps
        task.update_status(new_status, remarks)
        
        # Save to shared state
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        
        # Save to database if enabled
        if self.use_database:
            if not self._sync_task_to_database(task):
                # Rollback in-memory state to prevent desync
                task.status = old_status
                self._shared_tasks.set(task_id, task)
                self._tasks[task_id] = task
                logger.error(f"Failed to persist task {task_id} status change ({old_status} -> {new_status}) to database. Rolled back in-memory state.")
                raise TaskStateError(f"Persistence failure for task {task_id}. Database synchronization failed.")
            
            # Log audit to database
            if self._audit_dao:
                try:
                    self._audit_dao.log_action(
                        task_id=task_id,
                        action="TASK_STATUS_UPDATED",
                        operator_id="system",
                        old_status=old_status.value,
                        new_status=new_status.value,
                        details={"remarks": remarks}
                    )
                except Exception as audit_err:
                     logger.error(f"Failed to log task audit: {audit_err}")
                     raise
        
        # Record audit to transcript (legacy)
        self._record_audit(task_id, "TASK_STATUS_UPDATED", {"new_status": new_status, "remarks": remarks})

        return task

    def delete_task(self, task_id: str, *, force: bool = False) -> bool:
        """Delete a task through the official service boundary."""
        task = self.get_task(task_id)
        if task is None:
            return False
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")

        deleted = self._task_dao.delete_task(task_id, force=force)
        if not deleted:
            return False

        self._shared_tasks.delete(task_id)
        self._tasks.pop(task_id, None)
        if task.idempotency_key:
            self._shared_idempotency.delete(task.idempotency_key)
            self._idempotency_log.pop(task.idempotency_key, None)
            if self._idempotency_dao:
                self._idempotency_dao.delete(task.idempotency_key)

        self._record_audit(task_id, "TASK_DELETED", {"force": force})
        return True

    async def intervene(
        self,
        task_id: str,
        *,
        action: str,
        idempotency_key: str,
        remarks: Optional[str] = None,
        operator_id: str = "web-console-operator",
    ) -> Dict[str, Any]:
        """
        Apply an operator intervention with strict idempotency.

        Redlines:
        - every intervention MUST carry an idempotency_key
        - repeated calls with the same key must be replay-safe
        - intervention must be auditable in transcript_store
        """
        if not idempotency_key or not str(idempotency_key).strip():
            raise ValueError("idempotency_key is required")

        cached = self._intervention_receipts.get(idempotency_key)
        if cached is not None:
            return {**cached, "idempotent_replay": True}

        status_map = {
            "pause": TaskStatus.BLOCKED,
            "resume": TaskStatus.IN_PROGRESS,
            "approve": TaskStatus.DONE,
            "reject": TaskStatus.FAILED,
            "suspend": TaskStatus.SUSPENDED,
            "archive": TaskStatus.ARCHIVED,
        }
        new_status = status_map.get(action)
        if new_status is None:
            raise ValueError("Invalid intervention action")

        updated = await self.update_task_status(task_id, new_status, remarks=remarks)
        receipt = {
            "idempotency_key": idempotency_key,
            "task_id": task_id,
            "action": action,
            "new_status": updated.status.value,
            "remarks": remarks,
            "operator_id": operator_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._intervention_receipts[idempotency_key] = receipt
        if self._intervention_dao:
            self._intervention_dao.record_intervention(receipt)
        self._record_audit(
            task_id,
            "TASK_INTERVENED",
            {
                "idempotency_key": idempotency_key,
                "action": action,
                "new_status": updated.status.value,
                "remarks": remarks,
                "operator_id": operator_id,
            },
        )
        return {**receipt, "idempotent_replay": False}

    async def suspend_task(self, 
                    task_id: str, 
                    reason: str,
                    recovery_conditions: Optional[List[str]] = None,
                    auto_resume_at: Optional[datetime] = None,
                    suspension_context: Optional[Dict[str, Any]] = None) -> ZentexTask:
        """Suspend a task with recovery context"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if task.status not in [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]:
            raise TaskStateError(f"Cannot suspend task in status: {task.status}")
            
        original_status = task.status
        task.update_status(TaskStatus.SUSPENDED, remarks=f"Suspended: {reason}")
        
        # Create suspension record (Shared)
        suspended_task = SuspendedTask(
            task_id=task_id,
            original_status=original_status,
            suspension_reason=reason,
            recovery_conditions=recovery_conditions or [],
            suspension_context=suspension_context or {},
            auto_resume_at=auto_resume_at
        )
        
        self._shared_suspensions.set(task_id, suspended_task)
        self._shared_tasks.set(task_id, task) # Update task status in shared store
        self._tasks[task_id] = task
        if not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist suspended task {task_id}")
        if self._suspended_dao:
            self._suspended_dao.suspend_task(
                {
                    "task_id": task_id,
                    "original_status": original_status.value,
                    "suspension_reason": reason,
                    "recovery_conditions": recovery_conditions or [],
                    "suspension_context": suspension_context or {},
                    "suspended_at": suspended_task.suspended_at.isoformat(),
                    "auto_resume_at": auto_resume_at.isoformat() if auto_resume_at else None,
                }
            )
        
        self._record_audit(task_id, "TASK_SUSPENDED", {
            "reason": reason,
            "recovery_conditions": recovery_conditions,
            "auto_resume_at": auto_resume_at.isoformat() if auto_resume_at else None
        })
        
        return task

    async def resume_task(self, task_id: str, remarks: Optional[str] = None) -> ZentexTask:
        """Resume a suspended task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if task.status != TaskStatus.SUSPENDED:
            raise TaskStateError(f"Task {task_id} is not suspended")
            
        suspension_info = self._shared_suspensions.get(task_id, SuspendedTask)
        if not suspension_info:
            raise KeyError(f"No suspension info found for task {task_id}")
            
        # Restore original status
        task.update_status(suspension_info.original_status, 
                          remarks=remarks or f"Resumed from suspension: {suspension_info.suspension_reason}")
        
        # Clean up suspension record
        self._shared_suspensions.delete(task_id)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist resumed task {task_id}")
        if self._suspended_dao:
            self._suspended_dao.resume_task(task_id)
        
        self._record_audit(task_id, "TASK_RESUMED", {
            "original_status": suspension_info.original_status.value,
            "suspension_reason": suspension_info.suspension_reason,
            "remarks": remarks
        })
        
        return task

    def get_suspended_task(self, task_id: str) -> Optional[SuspendedTask]:
        """Get suspension information for a task"""
        if self._suspended_dao:
            payload = self._suspended_dao.get_suspended_task(task_id)
            if payload:
                return SuspendedTask.model_validate(payload)
        return self._shared_suspensions.get(task_id, SuspendedTask)

    def list_suspended_tasks(
        self,
        *,
        task_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SuspendedTask]:
        """List suspended tasks with database-backed filtering and pagination."""
        if self._suspended_dao:
            return [
                SuspendedTask.model_validate(item)
                for item in self._suspended_dao.list_suspended_tasks(
                    task_id=task_id,
                    limit=limit,
                    offset=offset,
                )
            ]
        all_suspensions = self._shared_suspensions.list_all(SuspendedTask)
        suspensions = list(all_suspensions.values())
        if task_id:
            suspensions = [item for item in suspensions if item.task_id == task_id]
        return suspensions[max(0, int(offset)): max(0, int(offset)) + max(1, min(int(limit), 500))]

    def trigger_negotiation_scans(self) -> List[Any]:
        """
        Scan all current suspended tasks and generate negotiation requests.
        """
        suspended = self._list_suspended_tasks_for_internal_scan()
        new_negs = self.negotiation_generator.scan_for_gaps(suspended)
        
        for neg in new_negs:
             self._record_audit(
                 neg.target_task_id, 
                 "NEGOTIATION_GENERATED", 
                 {"negotiation_id": neg.negotiation_id, "gap": neg.gap_type}
             )
             
        return new_negs

    async def run_worker_cycle(self) -> Dict[str, Any]:
        """
        Execute one worker heartbeat cycle.
        Pulls TODO tasks, routes them, and executes them via plugins.
        """
        if not self._task_dao:
            logger.warning("run_worker_cycle invoked but database/DAO is unavailable.")
            return {"tasks_dispatched": 0}

        logger.info("TaskManagementService: Starting worker heartbeat cycle...")
        try:
            stats = await self._dispatch_manager.run_cycle(self._task_dao)
            return stats.__dict__ if hasattr(stats, "__dict__") else {}
        except Exception as e:
            logger.exception("Worker heartbeat cycle failed at service level: %s", e)
            return {"error": str(e)}

    async def check_auto_resume_tasks(self) -> List[ZentexTask]:
        """Check and auto-resume tasks whose auto_resume_at time has arrived.
        Also reclaims stale IN_PROGRESS tasks (G39).
        """
        if not self._auto_resume_leader.try_acquire():
            return [] # Only the leader node performs auto-resume and reclamation

        now = datetime.now(timezone.utc)
        processed_tasks = []
        
        # 1. Auto-resume suspended tasks
        all_suspensions = self._shared_suspensions.list_all(SuspendedTask)
        for task_id, suspension_info in all_suspensions.items():
            if suspension_info.auto_resume_at and suspension_info.auto_resume_at <= now:
                try:
                    resumed_task = self.resume_task(task_id, "Auto-resumed by system leader")
                    processed_tasks.append(resumed_task)
                    logger.info(f"Auto-resumed task {task_id}")
                except Exception as e:
                    # Forbidden: auto-resume failures must leave a traceback.
                    # Logging a plain error string here hides the real root cause
                    # and makes the scheduler look healthier than it is.
                    logger.exception("Failed to auto-resume task %s: %s", task_id, e)
        
        # 2. Reclaim stale IN_PROGRESS tasks (G39) in bounded database pages.
        in_progress_tasks: List[ZentexTask] = []
        offset = 0
        page_size = 500
        while True:
            page = self.list_tasks(status=TaskStatus.IN_PROGRESS, limit=page_size, offset=offset)
            in_progress_tasks.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        stale_threshold = 300 # Default 5 minutes
        
        for task in in_progress_tasks:
            # 1. Determine the effective stale threshold for this specific task
            # Priority: task metadata > service default (300s)
            stale_threshold = task.metadata.get("stale_timeout", 300)
            
            # Check last_updated_at instead of started_at to allow heartbeats
            elapsed = (now - task.last_updated_at).total_seconds()
            if elapsed > stale_threshold:
                try:
                    if task.contract.retriable:
                        logger.warning(f"Reclaiming stale task {task.task_id} (threshold={stale_threshold}s): resetting to TODO.")
                        await self.update_task_status(
                            task.task_id, 
                            TaskStatus.TODO, 
                            remarks=f"Reclaimed from stale IN_PROGRESS state after {elapsed:.0f}s (Threshold: {stale_threshold}s)."
                        )
                    else:
                        logger.error(f"Reclaiming stale task {task.task_id} (threshold={stale_threshold}s): non-retriable, marking FAILED.")
                        await self.update_task_status(
                            task.task_id, 
                            TaskStatus.FAILED, 
                            remarks=f"Reclaimed from stale IN_PROGRESS state after {elapsed:.0f}s (Non-retriable, Threshold: {stale_threshold}s)."
                        )
                    processed_tasks.append(task)
                except Exception as e:
                    logger.exception("Failed to reclaim stale task %s: %s", task.task_id, e)
        
        return processed_tasks

    async def check_timeout_and_republish_tasks(
        self,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Reclaim timed-out IN_PROGRESS tasks and republish retriable work.

        Forbidden behavior:
        - exposing a timeout recovery entry point but leaving it as a fake stub
        - swallowing lease parsing or recovery failures and pretending the scheduler is healthy
        Both behaviors hide real stuck-task faults and directly damage runtime stability.
        """
        now = datetime.now(timezone.utc)
        recovered: List[Dict[str, Any]] = []
        in_progress_tasks = self.list_tasks(
            status=TaskStatus.IN_PROGRESS,
            limit=max(1, min(int(limit), 500)) if limit is not None else 100,
            offset=0,
        )

        for task in in_progress_tasks:
            try:
                action = build_timeout_recovery_action(task, now=now)
                if action is None:
                    continue

                original_metadata = copy.deepcopy(task.metadata)

                try:
                    await self.update_task_metadata(task.task_id, action.metadata)
                    await self.update_task_status(
                        task.task_id,
                        action.new_status,
                        remarks=action.remarks,
                    )
                    if action.last_error is not None:
                        if not self._task_dao:
                            raise RuntimeError("Task DAO is unavailable")
                        extra_updates = {
                            "last_error": action.last_error[:2000],
                            "execution_finished_at": action.execution_finished_at,
                        }
                        if not self._task_dao.update_task(task.task_id, extra_updates):
                            raise TaskStateError(
                                f"Failed to persist timeout recovery fault for task {task.task_id}"
                            )
                except Exception:
                    current_task = self.get_task(task.task_id) or task
                    current_task.metadata = original_metadata
                    self._shared_tasks.set(task.task_id, current_task)
                    self._tasks[task.task_id] = current_task
                    if self.use_database:
                        self._sync_task_to_database(current_task)
                    raise

                logger.warning(
                    "Recovered in_progress task %s to %s during timeout recovery.",
                    task.task_id,
                    action.new_status.value,
                )
                recovered.append(action.result)
            except Exception as exc:
                # Forbidden: silently skipping broken lease state would make the scheduler
                # look healthy while timed-out tasks remain stuck forever.
                logger.exception(
                    "Task timeout recovery failed for %s: %s",
                    task.task_id,
                    exc,
                )

        return recovered

    async def bulk_update_status(self, 
                           task_ids: List[str], 
                           new_status: TaskStatus, 
                           remarks: Optional[str] = None) -> Dict[str, Any]:
        """Bulk update task status"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                updated_task = await self.update_task_status(task_id, new_status, remarks)
                results["success"].append({
                    "task_id": task_id,
                    "previous_status": updated_task.status,
                    "new_status": new_status
                })
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_STATUS_UPDATE", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "new_status": new_status.value,
            "remarks": remarks
        })
        
        return results

    async def bulk_suspend(self, 
                    task_ids: List[str], 
                    reason: str,
                    recovery_conditions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Bulk suspend tasks"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                suspended_task = await self.suspend_task(task_id, reason, recovery_conditions)
                results["success"].append({
                    "task_id": task_id,
                    "status": suspended_task.status
                })
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_SUSPEND", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "reason": reason,
            "recovery_conditions": recovery_conditions
        })
        
        return results

    def bulk_resume(self, task_ids: List[str], remarks: Optional[str] = None) -> Dict[str, Any]:
        """Bulk resume suspended tasks"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                resume_result = self.resume_task(task_id, remarks)
                if asyncio.iscoroutine(resume_result):
                    try:
                        asyncio.get_running_loop()
                    except RuntimeError:
                        resumed_task = asyncio.run(resume_result)
                    else:
                        from concurrent.futures import Future
                        import threading

                        future: Future[ZentexTask] = Future()

                        def _runner() -> None:
                            try:
                                future.set_result(asyncio.run(resume_result))
                            except Exception as exc:  # pragma: no cover
                                future.set_exception(exc)

                        thread = threading.Thread(target=_runner, daemon=True)
                        thread.start()
                        resumed_task = future.result()
                else:
                    resumed_task = resume_result
                results["success"].append({
                    "task_id": task_id,
                    "status": resumed_task.status
                })
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_RESUME", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "remarks": remarks
        })
        
        return {
            **results,
            "requested": len(task_ids),
            "resumed": len(results["success"]),
        }

    def bulk_delete(self, task_ids: List[str], force: bool = False) -> Dict[str, Any]:
        """Bulk delete tasks (with safety checks)"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                task = self.get_task(task_id)
                if not task:
                    results["failed"].append({
                        "task_id": task_id,
                        "error": "Task not found"
                    })
                    continue
                    
                # Safety checks
                if not force and task.status in [TaskStatus.IN_PROGRESS]:
                    results["failed"].append({
                        "task_id": task_id,
                        "error": "Cannot delete task in progress without force flag"
                    })
                    continue
                    
                # Check for dependent tasks
                dependent_tasks = self.get_dependent_tasks(task_id, limit=1)
                if dependent_tasks and not force:
                    results["failed"].append({
                        "task_id": task_id,
                        "error": f"Task has {len(dependent_tasks)} dependent tasks"
                    })
                    continue
                    
                if not self.delete_task(task_id, force=force):
                    results["failed"].append({
                        "task_id": task_id,
                        "error": "Official delete_task returned False"
                    })
                    continue
                    
                results["success"].append({
                    "task_id": task_id,
                    "title": task.title
                })
                
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_DELETE", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "force": force
        })
        
        return results

    def add_dependency(self, task_id: str, dependency_id: str) -> ZentexTask:
        """Add a dependency to a task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        dependency = self.get_task(dependency_id)
        if not dependency:
            raise KeyError(f"Dependency task {dependency_id} not found")
            
        if dependency_id in task.depends_on:
            logger.warning(f"Task {task_id} already depends on {dependency_id}")
            return task
            
        # Check for circular dependencies
        if self._would_create_circular_dependency(task_id, dependency_id):
            raise TaskStateError(f"Adding dependency {dependency_id} to {task_id} would create a circular dependency")
            
        task.depends_on.append(dependency_id)
        task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if self.use_database and not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist dependency update for task {task_id}")
        
        self._record_audit(task_id, "DEPENDENCY_ADDED", {
            "dependency_id": dependency_id,
            "new_dependencies": task.depends_on
        })
        
        return task

    def remove_dependency(self, task_id: str, dependency_id: str) -> ZentexTask:
        """Remove a dependency from a task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if dependency_id not in task.depends_on:
            logger.warning(f"Task {task_id} does not depend on {dependency_id}")
            return task
            
        task.depends_on.remove(dependency_id)
        task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if self.use_database and not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist dependency removal for task {task_id}")
        
        self._record_audit(task_id, "DEPENDENCY_REMOVED", {
            "dependency_id": dependency_id,
            "remaining_dependencies": task.depends_on
        })
        
        return task

    def get_dependency_tree(self, task_id: str, max_depth: int = 5) -> Dict[str, Any]:
        """Get dependency tree for a task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        def build_tree(current_id: str, depth: int) -> Dict[str, Any]:
            if depth >= max_depth:
                return {"task_id": current_id, "dependencies": [], "max_depth_reached": True}
                
            current_task = self.get_task(current_id)
            if not current_task:
                return {"task_id": current_id, "dependencies": [], "not_found": True}
                
            dependencies = []
            for dep_id in current_task.depends_on:
                dependencies.append(build_tree(dep_id, depth + 1))
                
            return {
                "task_id": current_id,
                "title": current_task.title,
                "status": current_task.status.value,
                "dependencies": dependencies,
                "depth": depth
            }
            
        return build_tree(task_id, 0)

    def get_dependent_tasks(
        self,
        task_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ZentexTask]:
        """Get tasks that depend on the given task using database filtering."""
        if self.use_database and self._task_dao:
            rows = self._task_dao.list_tasks_depending_on(
                task_id,
                limit=limit,
                offset=offset,
            )
            tasks = [self._dict_to_task(row) for row in rows]
            for task in tasks:
                self._tasks[task.task_id] = task
                self._shared_tasks.set(task.task_id, task)
            return tasks
        tasks = [task for task in self._tasks.values() if task_id in task.depends_on]
        return tasks[max(0, int(offset)): max(0, int(offset)) + max(1, min(int(limit), 500))]

    def can_execute_task(self, task_id: str) -> Dict[str, Any]:
        """Check if a task can be executed based on its dependencies"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if task.status != TaskStatus.TODO:
            return {
                "can_execute": False,
                "reason": f"Task is in status: {task.status.value}",
                "dependencies_satisfied": False
            }
            
        unsatisfied_deps = []
        for dep_id in task.depends_on:
            dep_task = self.get_task(dep_id)
            if not dep_task or dep_task.status != TaskStatus.DONE:
                unsatisfied_deps.append({
                    "task_id": dep_id,
                    "status": dep_task.status.value if dep_task else "not_found",
                    "title": dep_task.title if dep_task else "Unknown"
                })
                
        return {
            "can_execute": len(unsatisfied_deps) == 0,
            "reason": "All dependencies satisfied" if not unsatisfied_deps else f"Waiting for {len(unsatisfied_deps)} dependencies",
            "dependencies_satisfied": len(unsatisfied_deps) == 0,
            "unsatisfied_dependencies": unsatisfied_deps
        }

    def _would_create_circular_dependency(self, task_id: str, new_dependency_id: str) -> bool:
        """Check if adding a dependency would create a circular dependency"""
        def check_circular(current_id: str, target_id: str, visited: set) -> bool:
            if current_id == target_id:
                return True
            if current_id in visited:
                return False
                
            visited.add(current_id)
            current_task = self.get_task(current_id)
            if not current_task:
                return False
                
            for dep_id in current_task.depends_on:
                if check_circular(dep_id, target_id, visited):
                    return True
                    
            return False
            
        return check_circular(new_dependency_id, task_id, set())

    def save_state(self) -> bool:
        return True

    def get_persistence_stats(self) -> Optional[Dict[str, Any]]:
        return None

    def _record_audit(self, task_id: str, action: str, details: Dict[str, Any]):
        if self.transcript_store is None or not callable(getattr(self.transcript_store, "write_entry", None)):
            return
        normalized_details = self._normalize_audit_value(details)
        self.transcript_store.write_entry(
            session_id="task-management-audit",
            turn_id=str(uuid4()),
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
            source="TaskManagementService",
            trace_id=f"task-audit:{task_id}:{action.lower()}",
            payload={
                "task_id": task_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": normalized_details
            }
        )

    def _normalize_audit_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
            return self._normalize_audit_value(value.model_dump(mode="json"))
        if hasattr(value, "value"):
            return self._normalize_audit_value(value.value)
        if isinstance(value, dict):
            return {str(k): self._normalize_audit_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._normalize_audit_value(v) for v in value]
        return str(value)

    def _record_task_outcome(
        self,
        *,
        task: ZentexTask,
        result: Dict[str, Any],
        verification_result: Any,
    ) -> Dict[str, Any]:
        return task_outcomes.record_task_outcome(
            outcome_dao=self._outcome_dao,
            task=task,
            result=result,
            verification_result=verification_result,
        )

    def get_task_outcome(self, task_id: str) -> Optional[Dict[str, Any]]:
        if not self._outcome_dao:
            raise RuntimeError("Task outcome DAO is unavailable")
        return self._outcome_dao.get_outcome(task_id)

    def write_task_outcome_to_reflection(self, reflection_service: Any, task_id: str) -> Dict[str, Any]:
        return task_outcomes.write_task_outcome_to_reflection(self, reflection_service, task_id)

    def write_task_outcome_to_memory(self, memory_service: Any, task_id: str) -> Dict[str, Any]:
        return task_outcomes.write_task_outcome_to_memory(self, memory_service, task_id)

    def write_task_outcome_to_learning(self, learning_service: Any, task_id: str) -> Dict[str, Any]:
        return task_outcomes.write_task_outcome_to_learning(self, learning_service, task_id)
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计信息，支持数据库和内存两种模式"""
        try:
            # Use database statistics if available
            if self.use_database and self._task_dao:
                db_stats = self._task_dao.get_task_statistics()
                
                # Get suspended tasks count
                suspended_count = 0
                if self._suspended_dao:
                    suspended_count = self._suspended_dao.count_suspended_tasks()
                
                # Calculate active tasks
                active_tasks = db_stats.get('todo_count', 0) + db_stats.get('in_progress_count', 0)
                
                return {
                    "total_tasks": db_stats.get('total_tasks', 0),
                    "tasks_by_status": {
                        "todo": db_stats.get('todo_count', 0),
                        "in_progress": db_stats.get('in_progress_count', 0),
                        "done": db_stats.get('done_count', 0),
                        "failed": db_stats.get('failed_count', 0),
                        "suspended": db_stats.get('suspended_count', 0),
                        "blocked": db_stats.get('blocked_count', 0),
                    },
                    "tasks_by_priority": {},  # Would need additional query
                    "tasks_by_type": {},  # Would need additional query
                    "tasks_today": 0,  # Would need date-based query
                    "suspended_tasks": suspended_count,
                    "active_tasks": active_tasks,
                    "completed_tasks": db_stats.get('done_count', 0),
                    "failed_tasks": db_stats.get('failed_count', 0),
                    "avg_progress": db_stats.get('avg_progress', 0.0),
                    "source": "database"
                }
            
            # Fallback to in-memory statistics
            tasks = list(self._tasks.values())
            
            # 基础统计
            total_tasks = len(tasks)
            
            # 按状态统计
            status_counts = {}
            for task in tasks:
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # 按优先级统计
            priority_counts = {}
            for task in tasks:
                priority = task.priority.value
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            # 按类型统计
            type_counts = {}
            for task in tasks:
                task_type = task.task_type.value
                type_counts[task_type] = type_counts.get(task_type, 0) + 1
            
            # 时间统计
            from datetime import datetime, timezone, timedelta
            today = datetime.now(timezone.utc).date()
            today_tasks = len([t for t in tasks if t.created_at.date() == today])
            
            # 挂起任务统计
            suspended_count = len(self._suspended_tasks)
            
            return {
                "total_tasks": total_tasks,
                "tasks_by_status": status_counts,
                "tasks_by_priority": priority_counts,
                "tasks_by_type": type_counts,
                "tasks_today": today_tasks,
                "suspended_tasks": suspended_count,
                "active_tasks": status_counts.get("todo", 0) + status_counts.get("in_progress", 0),
                "completed_tasks": status_counts.get("done", 0),
                "failed_tasks": status_counts.get("failed", 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get task statistics: {e}")
            return {
                "total_tasks": 0,
                "error": str(e)
            }

    # === Verification Methods ===
    
    async def complete_task_with_verification(
        self, 
        task_id: str, 
        result: Dict[str, Any],
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete a task with verification workflow.
        
        This method implements the full verification flow:
        1. Check if verification is enabled for the task
        2. Transition to WAITING_CONFIRMATION state
        3. Execute verification engine
        4. Based on results: accept/retry/escalate/reject
        
        Args:
            task_id: Task ID
            result: Worker's submission result (output, metadata, etc.)
            remarks: Optional remarks
            
        Returns:
            Dict containing completion status and verification result
        """
        task = self.get_task(task_id)
        if not task:
            return {
                "success": False,
                "error": f"Task {task_id} not found",
                "error_code": "TASK_NOT_FOUND"
            }

        async def _complete_without_verification(message: str) -> Dict[str, Any]:
            current = self.get_task(task_id)
            if current and current.status == TaskStatus.TODO:
                await self.update_task_status(
                    task_id,
                    TaskStatus.IN_PROGRESS,
                    "Auto-claimed before completion",
                )
            updated_task = await self.update_task_status(task_id, TaskStatus.DONE, remarks)
            return {
                "success": True,
                "task": updated_task.model_dump(),
                "verification_skipped": True,
                "message": message,
            }
        
        # Check if verification is available and enabled
        if not VERIFICATION_AVAILABLE or not self._verification_engine:
            logger.warning(f"Verification engine not available, completing task {task_id} without verification")
            return await _complete_without_verification(
                "Task completed without verification (engine not available)"
            )
        
        # Check if verification is enabled for this task
        if not task.contract.verification.enabled:
            logger.debug(f"Verification disabled for task {task_id}, completing directly")
            return await _complete_without_verification(
                "Task completed (verification disabled for this task)"
            )
        
        try:
            if task.status == TaskStatus.TODO:
                await self.update_task_status(
                    task_id,
                    TaskStatus.IN_PROGRESS,
                    "Auto-claimed before verification",
                )
                task = self.get_task(task_id) or task

            # Step 1: Transition to WAITING_CONFIRMATION
            logger.info(f"Task {task_id} entering verification phase")
            await self.update_task_status(
                task_id, 
                TaskStatus.WAITING_CONFIRMATION, 
                remarks="Waiting for verification"
            )
            
            # Step 2: Execute verification
            verification_result = await self._verification_engine.execute_verification(
                task=task,
                result=result
            )
            
            # Step 3: Record verification result in transcript
            self._record_audit(
                task_id,
                "TASK_VERIFICATION_COMPLETED",
                {
                    "overall_passed": verification_result.overall_passed,
                    "strategy": verification_result.strategy,
                    "confidence_score": verification_result.confidence_score,
                    "summary": verification_result.summary,
                    "recommendation": verification_result.recommendation,
                    "verifier_count": len(verification_result.verifier_results),
                    "execution_time_ms": verification_result.total_execution_time_ms
                }
            )
            
            # Step 4: Handle based on recommendation
            if verification_result.overall_passed:
                # Verification passed - complete the task
                final_remarks = f"Verified: {verification_result.summary}"
                if remarks:
                    final_remarks += f" | {remarks}"
                    
                updated_task = await self.update_task_status(
                    task_id,
                    TaskStatus.DONE,
                    remarks=final_remarks
                )
                task_outcome = self._record_task_outcome(
                    task=updated_task,
                    result=result,
                    verification_result=verification_result,
                )
                
                logger.info(f"Task {task_id} verified and completed successfully")
                return {
                    "success": True,
                    "task": updated_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "task_outcome": task_outcome,
                    "message": "Task completed and verified successfully"
                }
            
            else:
                # Verification failed - handle based on recommendation
                return await self._handle_verification_failure(
                    task_id, 
                    verification_result,
                    result,
                    remarks
                )
                
        except Exception as e:
            logger.error(f"Verification failed for task {task_id}: {e}")
            import traceback
            traceback.print_exc()
            
            # On error, mark task as failed
            try:
                updated_task = await self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    remarks=f"Verification error: {str(e)}"
                )
                return {
                    "success": False,
                    "task": updated_task.model_dump(),
                    "error": str(e),
                    "error_code": "VERIFICATION_ERROR"
                }
            except Exception as inner_e:
                logger.error(f"Failed to update task status after verification error: {inner_e}")
                return {
                    "success": False,
                    "error": f"Verification error: {str(e)}, Status update error: {str(inner_e)}",
                    "error_code": "VERIFICATION_AND_STATUS_ERROR"
                }
    
    async def _handle_verification_failure(
        self,
        task_id: str,
        verification_result: Any,
        result: Optional[Dict[str, Any]] = None,
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle verification failure based on recommendation.
        
        Args:
            task_id: Task ID
            verification_result: Verification result object
            remarks: Optional remarks
            
        Returns:
            Dict containing handling result
        """
        task = self.get_task(task_id)
        recommendation = verification_result.recommendation
        
        logger.warning(
            f"Verification failed for task {task_id}, "
            f"recommendation: {recommendation}"
        )
        
        if recommendation == "retry":
            # Retry: go back to IN_PROGRESS
            retry_remarks = f"Verification failed, auto-retrying: {verification_result.summary}"
            if remarks:
                retry_remarks += f" | {remarks}"
                
            updated_task = await self.update_task_status(
                task_id,
                TaskStatus.IN_PROGRESS,
                remarks=retry_remarks
            )
            task_outcome = self._record_task_outcome(
                task=updated_task,
                result=result or {},
                verification_result=verification_result,
            )
            
            logger.info(f"Task {task_id} set to IN_PROGRESS for retry")
            return {
                "success": True,
                "task": updated_task.model_dump(),
                "verification_result": verification_result.model_dump(),
                "task_outcome": task_outcome,
                "action_taken": "retry",
                "message": "Task set to IN_PROGRESS for automatic retry"
            }
            
        elif recommendation == "escalate":
            # Escalate: create manual review task or suspend
            escalation_target = task.contract.verification.escalation_target
            
            if escalation_target:
                # Create escalation notification
                self._record_audit(
                    task_id,
                    "TASK_VERIFICATION_ESCALATED",
                    {
                        "escalation_target": escalation_target,
                        "verification_summary": verification_result.summary,
                        "failed_verifiers": [
                            r.verifier_id 
                            for r in verification_result.verifier_results 
                            if not r.passed
                        ]
                    }
                )
                
                # Suspend the task pending manual review
                suspension_reason = f"Verification failed, escalated to {escalation_target}"
                suspended_task = await self.suspend_task(
                    task_id,
                    reason=suspension_reason,
                    recovery_conditions=[f"Manual review by {escalation_target}"]
                )
                task_outcome = self._record_task_outcome(
                    task=suspended_task,
                    result=result or {},
                    verification_result=verification_result,
                )
                
                logger.info(f"Task {task_id} escalated to {escalation_target}")
                return {
                    "success": True,
                    "task": suspended_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "task_outcome": task_outcome,
                    "action_taken": "escalated",
                    "escalation_target": escalation_target,
                    "message": f"Task escalated to {escalation_target} for manual review"
                }
            else:
                # No escalation target, just fail
                fail_remarks = f"Verification failed: {verification_result.summary}"
                if remarks:
                    fail_remarks += f" | {remarks}"
                    
                updated_task = await self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    remarks=fail_remarks
                )
                task_outcome = self._record_task_outcome(
                    task=updated_task,
                    result=result or {},
                    verification_result=verification_result,
                )
                
                return {
                    "success": False,
                    "task": updated_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "task_outcome": task_outcome,
                    "action_taken": "failed",
                    "message": "Task failed verification (no escalation target configured)"
                }
                
        else:  # recommendation == "reject"
            # Reject: mark as failed
            fail_remarks = f"Verification rejected: {verification_result.summary}"
            if remarks:
                fail_remarks += f" | {remarks}"
                
            updated_task = await self.update_task_status(
                task_id,
                TaskStatus.FAILED,
                remarks=fail_remarks
            )
            task_outcome = self._record_task_outcome(
                task=updated_task,
                result=result or {},
                verification_result=verification_result,
            )
            
            logger.info(f"Task {task_id} failed verification and rejected")
            return {
                "success": False,
                "task": updated_task.model_dump(),
                "verification_result": verification_result.model_dump(),
                "task_outcome": task_outcome,
                "action_taken": "rejected",
                "message": "Task failed verification and rejected"
            }
    
    def get_verification_engine_status(self) -> Dict[str, Any]:
        """
        Get verification engine status and configuration.
        
        Returns:
            Dict containing verification engine status
        """
        if not VERIFICATION_AVAILABLE:
            return {
                "available": False,
                "message": "Verification module not installed"
            }
        
        if not self._verification_engine:
            return {
                "available": True,
                "initialized": False,
                "message": "Verification engine not initialized"
            }
        
        # Get registered verifier types
        verifier_types = {}
        if self._verifier_registry:
            verifier_types = {
                k: v.__name__ 
                for k, v in self._verifier_registry.list_verifiers().items()
            }
        
        return {
            "available": True,
            "initialized": True,
            "registered_verifiers": verifier_types,
            "verifier_count": len(verifier_types),
            "message": "Verification engine ready"
        }

    # === Observability Methods (Phase F) ===

    def get_verification_records(self, task_id: str) -> List[Dict[str, Any]]:
        """Phase F: Retrieve real verification history from audit logs."""
        if not self.transcript_store:
            return []
        prefix = f"task-audit:{task_id}:task_verification_completed"
        entries = self.transcript_store.read_entries_by_trace_prefix(prefix)
        return [e.payload for e in entries if e.payload]

    def get_dispatch_records(self, task_id: str) -> List[Dict[str, Any]]:
        """Phase F: Retrieve real dispatch routing decisions from audit logs."""
        if not self.transcript_store:
            return []
        prefix = f"task-audit:{task_id}:task_dispatched"
        entries = self.transcript_store.read_entries_by_trace_prefix(prefix)
        return [e.payload for e in entries if e.payload]

    def get_supervision_records(self, task_id: str) -> List[Dict[str, Any]]:
        """Phase F: Retrieve real supervision/intervention records from audit logs."""
        if not self.transcript_store:
            return []
        prefix = f"task-audit:{task_id}:task_intervened"
        entries = self.transcript_store.read_entries_by_trace_prefix(prefix)
        # Also include other supervision-related events if needed
        return [e.payload for e in entries if e.payload]

    def get_database_status(self) -> Dict[str, Any]:
        """
        Get database layer status and statistics.
        
        Returns:
            Dict containing database status information
        """
        if not DATABASE_AVAILABLE:
            return {
                "available": False,
                "message": "Database module not available"
            }
        
        if not self.use_database:
            return {
                "available": True,
                "enabled": False,
                "message": "Task database layer unavailable"
            }
        
        try:
            # Get task statistics from database
            stats = self._task_dao.get_task_statistics() if self._task_dao else {}
            
            # Get cache info
            cache_info = {
                "size": self._cache.size() if self._cache else 0,
                "max_size": self._cache._max_size if self._cache else 0,
            } if self._cache else {}
            
            return {
                "available": True,
                "enabled": True,
                "db_path": str(self._db.db_path) if self._db else None,
                "statistics": stats,
                "cache": cache_info,
                "daos_initialized": {
                    "task_dao": self._task_dao is not None,
                    "suspended_dao": self._suspended_dao is not None,
                    "audit_dao": self._audit_dao is not None,
                    "intervention_dao": self._intervention_dao is not None,
                    "idempotency_dao": self._idempotency_dao is not None,
                },
                "message": "Database layer operational"
            }
        except Exception as e:
            return {
                "available": True,
                "enabled": True,
                "error": str(e),
                "message": "Database layer error"
            }

    def _list_tasks_for_internal_scan(self, *, page_size: int = 500) -> List[ZentexTask]:
        """Read task rows in bounded database pages for whole-state diagnostics."""
        tasks: List[ZentexTask] = []
        offset = 0
        capped_page_size = max(1, min(int(page_size), 500))
        while True:
            page = self.list_tasks(limit=capped_page_size, offset=offset)
            tasks.extend(page)
            if len(page) < capped_page_size:
                return tasks
            offset += capped_page_size

    def _list_suspended_tasks_for_internal_scan(self, *, page_size: int = 500) -> List[SuspendedTask]:
        """Read suspended task rows in bounded database pages for diagnostics."""
        suspended_tasks: List[SuspendedTask] = []
        offset = 0
        capped_page_size = max(1, min(int(page_size), 500))
        while True:
            page = self.list_suspended_tasks(limit=capped_page_size, offset=offset)
            suspended_tasks.extend(page)
            if len(page) < capped_page_size:
                return suspended_tasks
            offset += capped_page_size

    def diagnose_task_management_closure(self, *, stale_after_seconds: int = 300) -> Dict[str, Any]:
        """Return the feature-61 task lifecycle diagnostic report."""
        tasks = self._list_tasks_for_internal_scan()
        suspended_tasks = self._list_suspended_tasks_for_internal_scan()
        audit_history = self._collect_task_audit_history(tasks)
        report = build_task_lifecycle_diagnostic_report(
            tasks=tasks,
            suspended_tasks=suspended_tasks,
            audit_history_by_task_id=audit_history,
            stale_after_seconds=stale_after_seconds,
        )
        self._record_audit(
            "task_management",
            "TASK_MANAGEMENT_CLOSURE_DIAGNOSED",
            report.model_dump(mode="json"),
        )
        return report.model_dump(mode="json")

    def run_task_fault_injection_matrix(self, *, stale_after_seconds: int = 300) -> Dict[str, Any]:
        """Return the feature-61 fault injection matrix derived from real task state."""
        tasks = self._list_tasks_for_internal_scan()
        diagnostic = build_task_lifecycle_diagnostic_report(
            tasks=tasks,
            suspended_tasks=self._list_suspended_tasks_for_internal_scan(),
            audit_history_by_task_id=self._collect_task_audit_history(tasks),
            stale_after_seconds=stale_after_seconds,
        )
        report = build_task_fault_injection_report(diagnostic)
        self._record_audit(
            "task_management",
            "TASK_MANAGEMENT_FAULT_MATRIX_EXECUTED",
            report.model_dump(mode="json"),
        )
        return report.model_dump(mode="json")

    def _collect_task_audit_history(self, tasks: List[ZentexTask]) -> Dict[str, List[Dict[str, Any]]]:
        if not self._audit_dao:
            return {task.task_id: [] for task in tasks}
        return {
            task.task_id: self._audit_dao.get_audit_history(task.task_id, limit=200)
            for task in tasks
        }


_TASK_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _task_get_path(payload: Any, field: str) -> Any:
    current = payload
    for part in str(field or "").split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current


def task_plugin_normalize_result(
    result: Any,
    *,
    source_kind: str = "generic",
    metadata: Dict[str, Any] = None,
) -> Dict[str, Any]:
    payload = dict(result) if isinstance(result, dict) else {"output": result}
    return {
        "normalized": True,
        "status": str(payload.get("status") or "done"),
        "source_kind": source_kind,
        "output": payload.get("output") if "output" in payload else payload,
        "structured_output": payload.get("structured_output") or payload.get("output"),
        "artifacts": list(payload.get("artifacts") or []),
        "warnings": list(payload.get("warnings") or []),
        "stdout": payload.get("stdout"),
        "stderr": payload.get("stderr"),
        "metrics": dict(payload.get("metrics") or {}),
        "execution_metadata": dict(payload.get("execution_metadata") or {}),
        "metadata": dict(metadata or {}),
        "error": payload.get("error"),
    }


def task_plugin_extract_evidence(
    result: Any,
    *,
    source_kind: str = "generic",
) -> Dict[str, Any]:
    payload = dict(result) if isinstance(result, dict) else {"summary": str(result)}
    summary = str(payload.get("summary") or payload.get("output") or "").strip()
    warnings = list(payload.get("warnings") or [])
    artifacts = list(payload.get("artifacts") or [])
    evidence: List[Dict[str, Any]] = []
    signals: List[str] = []

    if summary:
        evidence.append(
            {
                "evidence_type": "summary",
                "content": summary,
                "source": source_kind,
                "confidence": 0.9,
                "related_field": "summary",
            }
        )
    if warnings:
        signals.append("warnings_present")
        for warning in warnings:
            evidence.append(
                {
                    "evidence_type": "warning",
                    "content": str(warning),
                    "source": source_kind,
                    "confidence": 0.8,
                    "related_field": "warnings",
                }
            )
    if artifacts:
        signals.append("artifacts_present")
        for artifact in artifacts:
            evidence.append(
                {
                    "evidence_type": "artifact",
                    "content": str(artifact.get("path") if isinstance(artifact, dict) else artifact),
                    "source": source_kind,
                    "confidence": 0.95,
                    "related_field": "artifacts",
                }
            )
    if payload.get("stderr"):
        signals.append("stderr_present")
        evidence.append(
            {
                "evidence_type": "stderr",
                "content": str(payload.get("stderr")),
                "source": source_kind,
                "confidence": 0.85,
                "related_field": "stderr",
            }
        )
    if payload.get("error"):
        signals.append("error_present")
        evidence.append(
            {
                "evidence_type": "error",
                "content": str(payload.get("error")),
                "source": source_kind,
                "confidence": 0.95,
                "related_field": "error",
            }
        )

    return {
        "summary": summary,
        "signals": signals,
        "evidence": evidence,
        "evidence_items": {
            "artifact_count": len(artifacts),
            "warning_count": len(warnings),
            "evidence_count": len(evidence),
        },
        "failure_symptoms": [signal for signal in signals if signal in {"error_present", "stderr_present"}],
    }


def task_plugin_rule_based_verification(
    result: Any,
    *,
    rules: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = dict(result) if isinstance(result, dict) else {"value": result}
    failures: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    for rule in list(rules or []):
        rule_type = str(rule.get("type") or "").strip()
        field = str(rule.get("field") or "").strip()
        actual = _task_get_path(payload, field) if field else payload
        passed = True
        if rule_type == "required_field":
            passed = actual is not None
        elif rule_type == "equals":
            passed = actual == rule.get("expected")
        elif rule_type == "min_length":
            passed = len(str(actual or "")) >= int(rule.get("min_length") or 0)
        elif rule_type == "regex":
            import re
            passed = re.search(str(rule.get("pattern") or ""), str(actual or "")) is not None
        else:
            passed = False

        evidence.append({"rule_type": rule_type, "field": field, "passed": passed, "actual": actual})
        if not passed:
            failures.append({"rule_type": rule_type, "field": field, "actual": actual})

    failure_type = "incorrect_output"
    if any(item["rule_type"] == "required_field" for item in failures):
        failure_type = "missing_requirement"
    elif any(item["rule_type"] == "min_length" for item in failures):
        failure_type = "partial_output"

    passed = not failures
    failure_count = len(failures)
    confidence_score = 1.0 if not rules else max(0.0, 1.0 - (failure_count / max(len(rules), 1)))
    return {
        "passed": passed,
        "overall_status": "passed" if passed else "failed",
        "failure_count": failure_count,
        "confidence_score": round(confidence_score, 3),
        "retryable": False,
        "recommendation": "accept" if passed else "review_failed_rules",
        "output_quality_score": round(confidence_score, 3),
        "completeness_score": 1.0 if passed else max(0.0, 1.0 - failure_count / max(len(rules or []), 1)),
        "evidence": evidence,
        "failure_classification": {
            "failure_type": failure_type if failures else None,
            "severity": "medium" if failures else "none",
            "failures": failures,
        },
    }


def task_plugin_match_capabilities(
    *,
    required_capabilities: List[str],
    candidate_capabilities: List[str],
    preferred_capabilities: List[Optional[str]] = None,
    forbidden_capabilities: List[Optional[str]] = None,
    capability_aliases: Dict[str, List[Optional[str]]] = None,
) -> Dict[str, Any]:
    candidate = set(candidate_capabilities or [])
    aliases = capability_aliases or {}

    def _matches(capability: str) -> bool:
        if capability in candidate:
            return True
        return any(alias in candidate for alias in aliases.get(capability, []))

    required = list(required_capabilities or [])
    preferred = list(preferred_capabilities or [])
    forbidden = list(forbidden_capabilities or [])
    matched_required = [cap for cap in required if _matches(cap)]
    matched_preferred = [cap for cap in preferred if _matches(cap)]
    missing_required = [cap for cap in required if cap not in matched_required]
    conflicting = [cap for cap in forbidden if _matches(cap)]
    has_required = not missing_required and not conflicting
    score = len(matched_required) / len(required) if required else 1.0
    confidence = 1.0 if has_required else max(0.0, score - 0.2)
    return {
        "has_required_capabilities": has_required,
        "capability_match_score": round(score, 3),
        "matched_required": matched_required,
        "matched_preferred": matched_preferred,
        "missing_required": missing_required,
        "conflicting_capabilities": conflicting,
        "match_confidence": round(confidence, 3),
        "routing_evidence": {
            "required_count": len(required),
            "candidate_count": len(candidate),
            "preferred_count": len(preferred),
        },
    }


def task_plugin_check_constraints(
    *,
    constraints: Dict[str, Any],
    runtime_context: Dict[str, Any],
) -> Dict[str, Any]:
    hard_blockers: List[str] = []
    soft_warnings: List[str] = []
    missing_prerequisites: List[str] = []
    policy_violations: List[str] = []

    max_allowed_risk = str(constraints.get("max_allowed_risk") or "critical").lower()
    current_risk = str(runtime_context.get("risk_level") or "low").lower()
    if _TASK_RISK_ORDER.get(current_risk, 0) > _TASK_RISK_ORDER.get(max_allowed_risk, 0):
        hard_blockers.append(f"risk level {current_risk} exceeds allowed {max_allowed_risk}")

    if constraints.get("requires_heartbeat") and not runtime_context.get("supports_heartbeat"):
        hard_blockers.append("heartbeat required but unavailable")
    if constraints.get("requires_network") and not runtime_context.get("network_available"):
        hard_blockers.append("network required but unavailable")
    if constraints.get("requires_approval") and not runtime_context.get("approval_granted"):
        policy_violations.append("approval required but not granted")

    required_artifact_types = set(constraints.get("required_artifact_types") or [])
    available_artifact_types = set(runtime_context.get("available_artifact_types") or [])
    missing_types = sorted(required_artifact_types - available_artifact_types)
    if missing_types:
        missing_prerequisites.append(
            f"missing required artifact types: {', '.join(missing_types)}"
        )

    timeout_budget = constraints.get("timeout_budget_seconds")
    estimated_duration = runtime_context.get("estimated_duration_seconds")
    if timeout_budget is not None and estimated_duration is not None and float(estimated_duration) > float(timeout_budget):
        hard_blockers.append("estimated duration exceeds timeout budget")

    max_retry_budget = constraints.get("max_retry_budget")
    requested_retry_budget = runtime_context.get("requested_retry_budget")
    if max_retry_budget is not None and requested_retry_budget is not None and int(requested_retry_budget) > int(max_retry_budget):
        policy_violations.append("requested retry budget exceeds allowed maximum")

    violations = [*hard_blockers, *policy_violations, *missing_prerequisites]
    return {
        "allowed": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "hard_blockers": hard_blockers,
        "soft_warnings": soft_warnings,
        "missing_prerequisites": missing_prerequisites,
        "policy_violations": policy_violations,
        "budget_assessment": {
            "timeout_budget_seconds": timeout_budget,
            "estimated_duration_seconds": estimated_duration,
            "max_retry_budget": max_retry_budget,
            "requested_retry_budget": requested_retry_budget,
        },
    }


def task_plugin_plan_compensation(
    *,
    workspace: str,
    artifacts: List[Dict[str, Union[Any]], List[Any]],
    failure_type: str,
) -> Dict[str, Any]:
    workspace_path = Path(workspace).resolve()
    cleanup_targets: List[Dict[str, Any]] = []
    for artifact in list(artifacts or []):
        raw_path = artifact.get("path") if isinstance(artifact, dict) else artifact
        if not raw_path:
            continue
        candidate = (workspace_path / str(raw_path)).resolve()
        cleanup_targets.append(
            {
                "path": str(candidate),
                "exists": candidate.exists(),
                "within_workspace": workspace_path == candidate or workspace_path in candidate.parents,
            }
        )

    return {
        "planned": True,
        "compensation_type": "cleanup_and_handoff",
        "cleanup_target_count": len(cleanup_targets),
        "cleanup_targets": cleanup_targets,
        "planned_actions": [
            "collect_failure_evidence",
            "cleanup_generated_artifacts",
            "prepare_handoff_summary",
        ],
        "affected_resources": [item["path"] for item in cleanup_targets],
        "safe_to_auto_execute": all(item["within_workspace"] for item in cleanup_targets),
        "requires_human_confirmation": failure_type in {"incorrect_output", "security_violation"},
    }


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
    "TaskAutoLoopScheduler",
    "task_plugin_normalize_result",
    "task_plugin_extract_evidence",
    "task_plugin_rule_based_verification",
    "task_plugin_match_capabilities",
    "task_plugin_check_constraints",
    "task_plugin_plan_compensation",
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
