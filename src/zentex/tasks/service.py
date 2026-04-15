from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from zentex.tasks.models import ZentexTask, TaskStatus, TaskType, TaskContract, CoordinationMode, TaskPriority, SuspendedTask
from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.models.errors import TaskStateError
from zentex.tasks.registry import TaskRegistry
from zentex.tasks.persistence import TaskPersistence
from zentex.kernel import BrainTranscriptEntryType
from zentex.common.state import SharedStateStore
from zentex.common.locking import get_lock_for_resource
from zentex.common.coordination import LeaderElection
from zentex.tasks.management.negotiation import NegotiationGenerator
from zentex.tasks.core.llm_decomposer import LLMTaskDecomposerPlugin
from zentex.tasks.scheduling.loop_scheduler import TaskAutoLoopScheduler

# Database support
try:
    from zentex.tasks.dao import (
        TaskDAO,
        SuspendedTaskDAO,
        TaskAuditLogDAO,
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
        persistence: Optional[TaskPersistence] = None,
        *,
        allow_rule_based_test_stub: bool = False,
        auto_save: bool = True,
        use_database: bool = True,
        db_path: str = "runtime/data/zentex_core.db",
    ) -> None:
        self.registry = registry
        self.transcript_store = transcript_store
        self.persistence = persistence
        self.auto_save = auto_save
        self.use_database = use_database and DATABASE_AVAILABLE

        # Initialize database layer if enabled
        if self.use_database:
            try:
                self._db = DatabaseConnection(db_path)
                self._cache = LRUCache(max_size=1000, ttl_seconds=60)
                
                self._task_dao = TaskDAO(self._db, self._cache)
                self._suspended_dao = SuspendedTaskDAO(self._db, self._cache)
                self._audit_dao = TaskAuditLogDAO(self._db)
                self._intervention_dao = InterventionReceiptDAO(self._db)
                self._idempotency_dao = IdempotencyLogDAO(self._db, self._cache)
                
                logger.info(f"Task database layer initialized: {db_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize database layer: {e}. Falling back to JSON persistence.")
                self.use_database = False
        else:
            self._db = None
            self._cache = None
            self._task_dao = None
            self._suspended_dao = None
            self._audit_dao = None
            self._intervention_dao = None
            self._idempotency_dao = None
            logger.info("Database layer disabled, using JSON persistence")

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
        
        # Handle contract
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
                 target_id: Optional[str] = None,
                 overdue_only: bool = False) -> List[ZentexTask]:
        """List tasks with optional filtering."""
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if priority:
            tasks = [t for t in tasks if t.priority == priority]
        if tags:
            tasks = [t for t in tasks if any(tag in t.tags for tag in tags)]
        if parent_task_id:
            tasks = [t for t in tasks if t.parent_task_id == parent_task_id]
        if target_id:
            tasks = [t for t in tasks if t.target_id == target_id]
        if overdue_only:
            tasks = [t for t in tasks if t.is_overdue()]

        tasks.sort(key=lambda t: (t.get_priority_score(), t.created_at), reverse=True)
        return tasks

    def list_tasks_grouped(self) -> Dict[str, List[ZentexTask]]:
        """Return tasks partitioned into presentation groups.

        Business rule: which statuses belong to each group is a domain
        decision and must not leak into web_console routers.
        """
        return {
            "in_progress": self.list_tasks(status=TaskStatus.IN_PROGRESS),
            "pending": (
                self.list_tasks(status=TaskStatus.TODO)
                + self.list_tasks(status=TaskStatus.BLOCKED)
            ),
            "waiting_confirmation": self.list_tasks(status=TaskStatus.WAITING_CONFIRMATION),
            "completed": self.list_tasks(status=TaskStatus.DONE),
            "cancelled": (
                self.list_tasks(status=TaskStatus.FAILED)
                + self.list_tasks(status=TaskStatus.SUSPENDED)
                + self.list_tasks(status=TaskStatus.ARCHIVED)
            ),
        }

    @property
    def revision(self) -> int:
        """Monotonically increasing counter; 0 when the service has no tracker.

        Callers (e.g. WebSocket stream) use this to detect in-flight changes
        without accessing private attributes.
        """
        return getattr(self, "_revision", 0)

    def get_task(self, task_id: str) -> Optional[ZentexTask]:
        """Get a task by ID, checking shared state first, then database."""
        # Favor shared state as source of truth
        task = self._shared_tasks.get(task_id, ZentexTask)
        if task:
            return task
        
        # Fallback to database if enabled
        if self.use_database:
            task = self._load_task_from_database(task_id)
            if task:
                # Cache in shared state for future access
                self._shared_tasks.set(task_id, task)
        
        return task

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
        return self.get_task(existing_id)

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
            
            # Save to database if enabled
            if self.use_database:
                self._sync_task_to_database(task)
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

        self._record_audit(mission_task.task_id, "MISSION_DECOMPOSED", {"subtask_ids": mission_task.subtask_ids})
        self._save_to_persistence()

    async def claim_task(self, task_id: str, handler_id: str) -> ZentexTask:
        """
        Collaborative claiming of a subtask.
        """
        task = self.get_task(task_id)
        if not task:
             raise KeyError(f"Task {task_id} not found")
             
        # Check dependencies
        for dep_id in task.depends_on:
            dep_task = self._tasks.get(dep_id)
            if dep_task and dep_task.status != TaskStatus.DONE:
                raise TaskStateError(f"Dependency {dep_id} is not yet DONE.")

        task.target_id = handler_id
        return self.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks=f"Claimed by {handler_id}")

    def update_task_status(self, task_id: str, new_status: TaskStatus, remarks: Optional[str] = None):
        """
        State Machine Redline: Validates illegal transitions.
        Now with database persistence support.
        """
        task = self.get_task(task_id)  # Use get_task to check database too
        if not task:
            raise KeyError(f"Task {task_id} not found")

        # Define legal transitions
        legal_from: Dict[TaskStatus, List[TaskStatus]] = {
            TaskStatus.TODO: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.SUSPENDED, TaskStatus.ARCHIVED],
            TaskStatus.IN_PROGRESS: [TaskStatus.WAITING_CONFIRMATION, TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.SUSPENDED],
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
        
        # Save to database if enabled
        if self.use_database:
            self._sync_task_to_database(task)
            
            # Log audit to database
            if self._audit_dao:
                self._audit_dao.log_action(
                    task_id=task_id,
                    action="TASK_STATUS_UPDATED",
                    operator_id="system",
                    old_status=old_status.value,
                    new_status=new_status.value,
                    details={"remarks": remarks}
                )
        
        # Record audit to transcript (legacy)
        self._record_audit(task_id, "TASK_STATUS_UPDATED", {"new_status": new_status, "remarks": remarks})
        
        # Legacy persistence
        self._save_to_persistence()
        
        return task

    def intervene(
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

        updated = self.update_task_status(task_id, new_status, remarks=remarks)
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
        self._save_to_persistence()
        return {**receipt, "idempotent_replay": False}

    def suspend_task(self, 
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
        
        self._record_audit(task_id, "TASK_SUSPENDED", {
            "reason": reason,
            "recovery_conditions": recovery_conditions,
            "auto_resume_at": auto_resume_at.isoformat() if auto_resume_at else None
        })
        
        return task

    def resume_task(self, task_id: str, remarks: Optional[str] = None) -> ZentexTask:
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
        
        self._record_audit(task_id, "TASK_RESUMED", {
            "original_status": suspension_info.original_status.value,
            "suspension_reason": suspension_info.suspension_reason,
            "remarks": remarks
        })
        
        return task

    def get_suspended_task(self, task_id: str) -> Optional[SuspendedTask]:
        """Get suspension information for a task"""
        return self._shared_suspensions.get(task_id, SuspendedTask)

    def list_suspended_tasks(self) -> List[SuspendedTask]:
        """List all suspended tasks"""
        all_suspensions = self._shared_suspensions.list_all(SuspendedTask)
        return list(all_suspensions.values())

    def trigger_negotiation_scans(self) -> List[Any]:
        """
        Scan all current suspended tasks and generate negotiation requests.
        """
        suspended = self.list_suspended_tasks()
        new_negs = self.negotiation_generator.scan_for_gaps(suspended)
        
        for neg in new_negs:
             self._record_audit(
                 neg.target_task_id, 
                 "NEGOTIATION_GENERATED", 
                 {"negotiation_id": neg.negotiation_id, "gap": neg.gap_type}
             )
             
        return new_negs

    async def check_auto_resume_tasks(self) -> List[ZentexTask]:
        """Check and auto-resume tasks whose auto_resume_at time has arrived"""
        if not self._auto_resume_leader.try_acquire():
            return [] # Only the leader node performs auto-resume

        now = datetime.now(timezone.utc)
        resumed_tasks = []
        
        all_suspensions = self._shared_suspensions.list_all(SuspendedTask)
        for task_id, suspension_info in all_suspensions.items():
            if suspension_info.auto_resume_at and suspension_info.auto_resume_at <= now:
                try:
                    resumed_task = self.resume_task(task_id, "Auto-resumed by system leader")
                    resumed_tasks.append(resumed_task)
                    logger.info(f"Auto-resumed task {task_id}")
                except Exception as e:
                    logger.error(f"Failed to auto-resume task {task_id}: {e}")
        
        return resumed_tasks

    def bulk_update_status(self, 
                           task_ids: List[str], 
                           new_status: TaskStatus, 
                           remarks: Optional[str] = None) -> Dict[str, Any]:
        """Bulk update task status"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                updated_task = self.update_task_status(task_id, new_status, remarks)
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

    def bulk_suspend(self, 
                    task_ids: List[str], 
                    reason: str,
                    recovery_conditions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Bulk suspend tasks"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                suspended_task = self.suspend_task(task_id, reason, recovery_conditions)
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
                resumed_task = self.resume_task(task_id, remarks)
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
        
        return results

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
                dependent_tasks = [t for t in self._tasks.values() if task_id in t.depends_on]
                if dependent_tasks and not force:
                    results["failed"].append({
                        "task_id": task_id,
                        "error": f"Task has {len(dependent_tasks)} dependent tasks"
                    })
                    continue
                    
                # Delete the task
                del self._tasks[task_id]
                if task_id in self._suspended_tasks:
                    del self._suspended_tasks[task_id]
                    
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

    def get_dependent_tasks(self, task_id: str) -> List[ZentexTask]:
        """Get all tasks that depend on the given task"""
        return [task for task in self._tasks.values() if task_id in task.depends_on]

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

    def _load_from_persistence(self) -> None:
        """Load data from persistence layer"""
        if not self.persistence:
            return
            
        try:
            data = self.persistence.load_all()
            self._tasks = data.get("tasks", {})
            self._suspended_tasks = data.get("suspended_tasks", {})
            self._idempotency_log = data.get("idempotency_log", {})
            self._intervention_receipts = data.get("intervention_receipts", {})
            logger.info("Successfully loaded task data from persistence")
        except Exception as e:
            logger.error(f"Failed to load from persistence: {e}")

    def _save_to_persistence(self, tasks_only: bool = False) -> None:
        """Save data to persistence layer"""
        if not self.persistence or not self.auto_save:
            return
            
        try:
            if tasks_only:
                self.persistence.save_tasks_only(self._tasks)
            else:
                self.persistence.save_all(
                    self._tasks,
                    self._suspended_tasks,
                    self._idempotency_log,
                    self._intervention_receipts
                )
        except Exception as e:
            logger.error(f"Failed to save to persistence: {e}")

    def save_state(self) -> bool:
        """Manually trigger save of all state"""
        if not self.persistence:
            return False
        return self.persistence.save_all(
            self._tasks,
            self._suspended_tasks,
            self._idempotency_log,
            self._intervention_receipts
        )

    def get_persistence_stats(self) -> Optional[Dict[str, Any]]:
        """Get persistence statistics"""
        if not self.persistence:
            return None
        return self.persistence.get_storage_stats()

    def _record_audit(self, task_id: str, action: str, details: Dict[str, Any]):
        self.transcript_store.write_entry(
            session_id="task-management-audit",
            turn_id=str(uuid4()),
            entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
            source="TaskManagementService",
            trace_id=f"task-audit:{task_id}:{action.lower()}",
            payload={
                "task_id": task_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details
            }
        )
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计信息，支持数据库和内存两种模式"""
        try:
            # Use database statistics if available
            if self.use_database and self._task_dao:
                db_stats = self._task_dao.get_task_statistics()
                
                # Get suspended tasks count
                suspended_count = 0
                if self._suspended_dao:
                    suspended_tasks = self._suspended_dao.list_suspended_tasks()
                    suspended_count = len(suspended_tasks)
                
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
        
        # Check if verification is available and enabled
        if not VERIFICATION_AVAILABLE or not self._verification_engine:
            logger.warning(f"Verification engine not available, completing task {task_id} without verification")
            updated_task = self.update_task_status(task_id, TaskStatus.DONE, remarks)
            return {
                "success": True,
                "task": updated_task.model_dump(),
                "verification_skipped": True,
                "message": "Task completed without verification (engine not available)"
            }
        
        # Check if verification is enabled for this task
        if not task.contract.verification.enabled:
            logger.debug(f"Verification disabled for task {task_id}, completing directly")
            updated_task = self.update_task_status(task_id, TaskStatus.DONE, remarks)
            return {
                "success": True,
                "task": updated_task.model_dump(),
                "verification_skipped": True,
                "message": "Task completed (verification disabled for this task)"
            }
        
        try:
            # Step 1: Transition to WAITING_CONFIRMATION
            logger.info(f"Task {task_id} entering verification phase")
            self.update_task_status(
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
                    
                updated_task = self.update_task_status(
                    task_id,
                    TaskStatus.DONE,
                    remarks=final_remarks
                )
                
                logger.info(f"Task {task_id} verified and completed successfully")
                return {
                    "success": True,
                    "task": updated_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "message": "Task completed and verified successfully"
                }
            
            else:
                # Verification failed - handle based on recommendation
                return await self._handle_verification_failure(
                    task_id, 
                    verification_result,
                    remarks
                )
                
        except Exception as e:
            logger.error(f"Verification failed for task {task_id}: {e}")
            import traceback
            traceback.print_exc()
            
            # On error, mark task as failed
            try:
                updated_task = self.update_task_status(
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
                
            updated_task = self.update_task_status(
                task_id,
                TaskStatus.IN_PROGRESS,
                remarks=retry_remarks
            )
            
            logger.info(f"Task {task_id} set to IN_PROGRESS for retry")
            return {
                "success": True,
                "task": updated_task.model_dump(),
                "verification_result": verification_result.model_dump(),
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
                suspended_task = self.suspend_task(
                    task_id,
                    reason=suspension_reason,
                    recovery_conditions=[f"Manual review by {escalation_target}"]
                )
                
                logger.info(f"Task {task_id} escalated to {escalation_target}")
                return {
                    "success": True,
                    "task": suspended_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "action_taken": "escalated",
                    "escalation_target": escalation_target,
                    "message": f"Task escalated to {escalation_target} for manual review"
                }
            else:
                # No escalation target, just fail
                fail_remarks = f"Verification failed: {verification_result.summary}"
                if remarks:
                    fail_remarks += f" | {remarks}"
                    
                updated_task = self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    remarks=fail_remarks
                )
                
                return {
                    "success": False,
                    "task": updated_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "action_taken": "failed",
                    "message": "Task failed verification (no escalation target configured)"
                }
                
        else:  # recommendation == "reject"
            # Reject: mark as failed
            fail_remarks = f"Verification rejected: {verification_result.summary}"
            if remarks:
                fail_remarks += f" | {remarks}"
                
            updated_task = self.update_task_status(
                task_id,
                TaskStatus.FAILED,
                remarks=fail_remarks
            )
            
            logger.info(f"Task {task_id} failed verification and rejected")
            return {
                "success": False,
                "task": updated_task.model_dump(),
                "verification_result": verification_result.model_dump(),
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
                "message": "Database layer disabled, using JSON persistence"
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
    metadata: Dict[str, Any] | None = None,
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
    rules: List[Dict[str, Any]] | None = None,
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
    preferred_capabilities: List[str] | None = None,
    forbidden_capabilities: List[str] | None = None,
    capability_aliases: Dict[str, List[str]] | None = None,
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
    artifacts: List[Dict[str, Any]] | List[Any],
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
_default_service: TaskManagementService | None = None


def get_service() -> TaskManagementService:
    """Standard service factory function for launcher assembly.
    
    Returns the global TaskManagementService instance, creating it if necessary.
    This function is required by the SystemAssembler to initialize the tasks service.
    
    Note: This creates a minimal instance with default decomposer for startup.
    The service will be properly reconfigured by the kernel with actual dependencies.
    """
    global _default_service
    if _default_service is None:
        # Create a minimal instance with rule-based stub allowed for initial startup
        from zentex.tasks.registry import TaskRegistry
        _default_service = TaskManagementService(
            registry=TaskRegistry(),
            transcript_store=None,  # Will be set by kernel
            allow_rule_based_test_stub=True,  # Allow default decomposer for startup
        )
    return _default_service
