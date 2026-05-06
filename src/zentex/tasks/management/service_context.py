from __future__ import annotations

import asyncio
import copy
import inspect
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from zentex.common.locking import get_lock_for_resource
from zentex.common.storage_paths import get_storage_paths
from zentex.kernel import AuditEventType
from zentex.kernel.state_domain.transcript import NullTranscriptStore, TranscriptStore
from zentex.tasks import outcomes as task_outcomes
from zentex.tasks.decomposition.q9_subtask_validation import validate_q9_subtask_splitting_against_llm_output
from zentex.tasks.execution.assignment_flow import ResourceMatcher, TaskAssignmentRouter
from zentex.tasks.execution.assignment_projection import (
    attach_validated_execution_assignment as attach_validated_execution_assignment_projection,
    validate_execution_assignment as validate_execution_assignment_projection,
)
from zentex.tasks.decomposition.q9_blueprint_runtime import (
    dependency_graph_is_dag,
    q9_blueprint_capabilities,
    q9_blueprint_designated_executors,
    q9_blueprint_lines,
    q9_blueprint_step_records,
    q9_executor_for_capability,
    q9_executor_for_designation,
    q9_executor_runtime_metadata,
)
from zentex.tasks.lifecycle_diagnostics import (
    build_task_fault_injection_report,
    build_task_lifecycle_diagnostic_report,
)
from zentex.tasks.maintenance.garbage_analysis import (
    build_task_creation_analysis_report,
    build_task_garbage_analysis_report,
)
from zentex.tasks.models import (
    CoordinationMode,
    DecompositionContext,
    SuspendedTask,
    TaskContract,
    TaskPriority,
    TaskScope,
    TaskStatus,
    TaskType,
    ZentexTask,
)
from zentex.tasks.models.errors import TaskStateError
from zentex.tasks.timeout_recovery import build_timeout_recovery_action
from zentex.tasks.verification.status_bridge import maybe_route_done_status_update_through_verification

try:
    from zentex.tasks.dao import (
        IdempotencyLogDAO,
        InterventionReceiptDAO,
        SuspendedTaskDAO,
        TaskAuditLogDAO,
        TaskDAO,
        TaskOutcomeDAO,
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

try:
    from zentex.tasks.verification.engine import VerificationEngine
    from zentex.tasks.verification.models import VerificationResult as VerificationResultModel
    from zentex.tasks.verification.registry import VerifierRegistry

    VERIFICATION_AVAILABLE = True
except ImportError:
    VERIFICATION_AVAILABLE = False
    VerificationEngine = None
    VerifierRegistry = None
    VerificationResultModel = None

logger = logging.getLogger("zentex.tasks.management.task_management_service")
