from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class WorkflowNodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    WAITING_CONFIRMATION = "waiting_confirmation"


@dataclass(frozen=True)
class WorkflowRunContext:
    session_id: str
    trace_id: str
    turn_id: str = ""
    task_id: str = ""
    workflow_id: str = "workflow"
    workflow_name: str = "Workflow"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowNodeState:
    node_id: str
    node_name: str
    status: WorkflowNodeStatus | str
    trace_id: str
    session_id: str
    task_id: str = ""
    evidence_ref: str = ""
    error_code: str = ""
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = getattr(self.status, "value", self.status)
        return payload


@dataclass(frozen=True)
class WorkflowEvidence:
    status: str
    trace_id: str
    session_id: str
    task_id: str
    node_id: str
    node_name: str
    evidence_ref: str
    evidence: dict[str, Any] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    error_code: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowAuditAssertion:
    status: str
    trace_id: str
    session_id: str
    task_id: str = ""
    node_id: str = ""
    node_name: str = ""
    evidence_ref: str = ""
    checked_event_count: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    error_code: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExternalInvocationEvidence(WorkflowEvidence):
    executor_type: str = ""
    executor_id: str = ""
    invocation_ref: str = ""


@dataclass(frozen=True)
class WritebackEvidence(WorkflowEvidence):
    memory_verified: bool = False
    learning_verified: bool = False
    reflection_verified: bool = False


@dataclass(frozen=True)
class EvolutionEvidence(WorkflowEvidence):
    proactive_memory_retrieval_success: bool = False
    learning_applied_to_action_candidates: bool = False
    reflection_applied_to_posture: bool = False
    strategy_self_optimized: bool = False


def normalize_status(value: WorkflowNodeStatus | str) -> str:
    return str(getattr(value, "value", value) or "").strip()
