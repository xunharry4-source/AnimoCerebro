"""G31A autonomous control loop and resumable task state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Stimulus(BaseModel):
    """External or internal signal that may create autonomous work."""

    model_config = ConfigDict(extra="forbid")

    stimulus_id: str = Field(default_factory=lambda: f"stim-{uuid4().hex[:12]}")
    source: str
    event_type: str
    description: str
    risk_level: str = "medium"
    memory_refs: list[str] = Field(default_factory=list)
    agent_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AutonomousTask(BaseModel):
    """Resumable autonomous task controlled by the G31A state machine."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: f"auto-task-{uuid4().hex[:12]}")
    stimulus_id: str
    title: str
    status: str = "queued"
    priority: float
    risk_level: str
    acceptance_criteria: list[str]
    needs_confirmation: bool
    collaboration_required: bool
    blocked_reason: str | None = None
    trace_id: str = Field(default_factory=lambda: f"trace-{uuid4().hex[:12]}")
    review_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CycleReport(BaseModel):
    """One autonomous loop cycle result."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: str = Field(default_factory=lambda: f"cycle-{uuid4().hex[:12]}")
    tasks: list[AutonomousTask]
    nine_question_mapping: dict[str, Any]
    audit_events: list[dict[str, Any]]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AutonomousControlLoop:
    """Stimulus aggregation, task ranking, state transition, and audit ledger."""

    def __init__(self) -> None:
        self._stimuli: dict[str, Stimulus] = {}
        self._tasks: dict[str, AutonomousTask] = {}
        self._audit_events: list[dict[str, Any]] = []

    def ingest_stimulus(self, stimulus: Stimulus) -> Stimulus:
        """Persist a stimulus for the next cycle."""

        self._stimuli[stimulus.stimulus_id] = stimulus
        self._audit("stimulus_ingested", stimulus.stimulus_id, {"event_type": stimulus.event_type})
        return stimulus

    def run_cycle(self, *, budget_level: str = "normal") -> CycleReport:
        """Create and rank autonomous tasks from unprocessed stimuli."""

        new_tasks: list[AutonomousTask] = []
        for stimulus in self._stimuli.values():
            if any(task.stimulus_id == stimulus.stimulus_id for task in self._tasks.values()):
                continue
            priority = self._priority_for(stimulus, budget_level)
            needs_confirmation = stimulus.risk_level in {"high", "critical"}
            task = AutonomousTask(
                stimulus_id=stimulus.stimulus_id,
                title=f"Handle {stimulus.event_type}: {stimulus.description}",
                priority=priority,
                risk_level=stimulus.risk_level,
                acceptance_criteria=[
                    "decision has trace_id",
                    "risk boundary checked",
                    "result is written back to review notes",
                ],
                needs_confirmation=needs_confirmation,
                collaboration_required=bool(stimulus.agent_refs),
                status="waiting_confirmation" if needs_confirmation else "queued",
            )
            self._tasks[task.task_id] = task
            self._audit("task_created", task.task_id, {"stimulus_id": stimulus.stimulus_id, "priority": priority})
            new_tasks.append(task)
        ordered = sorted(self._tasks.values(), key=lambda item: item.priority, reverse=True)
        mapping = {
            "q1_where_am_i": "stimulus aggregation",
            "q3_role_inference": "memory_refs and agent_refs",
            "q4_what_can_i_do": "feasibility from budget and risk",
            "q8_what_should_i_do_now": [task.task_id for task in ordered],
            "q9_how_should_i_act": "state machine transition with audit",
            "budget_level": budget_level,
        }
        return CycleReport(tasks=ordered, nine_question_mapping=mapping, audit_events=list(self._audit_events))

    def transition_task(self, task_id: str, action: str, *, reason: str) -> AutonomousTask:
        """Transition a task through the allowed state machine."""

        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown autonomous task: {task_id}")
        transitions = {
            "start": {"queued": "in_progress"},
            "block": {"queued": "blocked", "in_progress": "blocked"},
            "suspend": {"queued": "suspended", "in_progress": "suspended", "blocked": "suspended"},
            "resume": {"suspended": "queued", "blocked": "queued"},
            "approve": {"waiting_confirmation": "queued"},
            "reject": {"waiting_confirmation": "archived"},
            "complete": {"in_progress": "done"},
            "archive": {"done": "archived", "rejected": "archived"},
        }
        next_status = transitions.get(action, {}).get(task.status)
        if next_status is None:
            raise ValueError(f"Illegal task transition: {task.status} -> {action}")
        updated = task.model_copy(
            update={
                "status": next_status,
                "blocked_reason": reason if next_status == "blocked" else None,
                "review_notes": [*task.review_notes, reason],
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._tasks[task_id] = updated
        self._audit("task_transition", task_id, {"action": action, "status": next_status, "reason": reason})
        return updated

    def get_task(self, task_id: str) -> AutonomousTask | None:
        """Return one task by id."""

        return self._tasks.get(task_id)

    def list_tasks(self) -> list[AutonomousTask]:
        """Return all autonomous tasks."""

        return list(self._tasks.values())

    def list_audit_events(self) -> list[dict[str, Any]]:
        """Return the autonomous loop audit ledger."""

        return list(self._audit_events)

    @staticmethod
    def _priority_for(stimulus: Stimulus, budget_level: str) -> float:
        risk_score = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}.get(stimulus.risk_level, 0.5)
        memory_score = min(0.2, 0.05 * len(stimulus.memory_refs))
        agent_score = min(0.2, 0.05 * len(stimulus.agent_refs))
        budget_penalty = 0.3 if budget_level == "low" else 0.0
        return max(0.0, min(1.0, risk_score + memory_score + agent_score - budget_penalty))

    def _audit(self, action: str, subject_id: str, payload: dict[str, Any]) -> None:
        self._audit_events.append(
            {
                "audit_id": f"auto-audit-{uuid4().hex[:12]}",
                "action": action,
                "subject_id": subject_id,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
