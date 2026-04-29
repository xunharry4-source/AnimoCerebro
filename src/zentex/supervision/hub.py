from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AutonomyMode(str, Enum):
    AUTONOMOUS = "autonomous"
    PAUSED = "paused"
    MANUAL = "manual"
    READ_ONLY = "read_only"
    FUSED = "fused"


class ThoughtTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    stage: str = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InterventionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intervention_id: str = Field(default_factory=lambda: str(uuid4()))
    action: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    before_mode: AutonomyMode
    after_mode: AutonomyMode
    confirmation_token: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SupervisionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AutonomyMode = AutonomyMode.AUTONOMOUS
    active_terminal_count: int = 0
    continuously_supervised: bool = False
    write_allowed: bool = True
    last_intervention_id: str | None = None


class SupervisionHub:
    def __init__(self) -> None:
        self._traces: list[ThoughtTrace] = []
        self._interventions: list[InterventionRecord] = []
        self._terminals: set[str] = set()
        self._mode = AutonomyMode.AUTONOMOUS

    def connect_terminal(self, terminal_id: str) -> SupervisionState:
        self._terminals.add(terminal_id)
        return self.get_state()

    def disconnect_terminal(self, terminal_id: str) -> SupervisionState:
        self._terminals.discard(terminal_id)
        return self.get_state()

    def append_thought_trace(self, trace: ThoughtTrace) -> ThoughtTrace:
        existing = [item for item in self._traces if item.session_id == trace.session_id and item.sequence == trace.sequence]
        if existing:
            raise ValueError(f"ThoughtTrace sequence {trace.sequence} already exists for session {trace.session_id}")
        self._traces.append(trace)
        self._traces.sort(key=lambda item: (item.session_id, item.sequence, item.created_at))
        return trace

    def list_thought_traces(self, *, session_id: str | None = None, after_sequence: int | None = None) -> list[ThoughtTrace]:
        rows = self._traces
        if session_id is not None:
            rows = [row for row in rows if row.session_id == session_id]
        if after_sequence is not None:
            rows = [row for row in rows if row.sequence > after_sequence]
        return list(rows)

    def apply_intervention(
        self,
        *,
        action: str,
        reason: str,
        operator_id: str,
        confirmation_token: str | None = None,
    ) -> InterventionRecord:
        before = self._mode
        after = self._next_mode(action, confirmation_token)
        record = InterventionRecord(
            action=action,
            operator_id=operator_id,
            reason=reason,
            before_mode=before,
            after_mode=after,
            confirmation_token=confirmation_token,
        )
        self._mode = after
        self._interventions.append(record)
        return record

    def list_interventions(self) -> list[InterventionRecord]:
        return list(self._interventions)

    def get_state(self) -> SupervisionState:
        return SupervisionState(
            mode=self._mode,
            active_terminal_count=len(self._terminals),
            continuously_supervised=len(self._terminals) > 0,
            write_allowed=self._mode == AutonomyMode.AUTONOMOUS,
            last_intervention_id=self._interventions[-1].intervention_id if self._interventions else None,
        )

    def assert_write_allowed(self, action_payload: dict[str, Any] | None = None) -> None:
        state = self.get_state()
        if not state.write_allowed:
            raise RuntimeError(f"Write operation blocked by SupervisionHub mode={state.mode.value}: {action_payload or {}}")

    def _next_mode(self, action: str, confirmation_token: str | None) -> AutonomyMode:
        normalized = action.strip().lower()
        if normalized == "pause_autonomy":
            return AutonomyMode.PAUSED
        if normalized == "manual_mode":
            return AutonomyMode.MANUAL
        if normalized == "read_only":
            return AutonomyMode.READ_ONLY
        if normalized == "physical_kill_switch":
            return AutonomyMode.FUSED
        if normalized == "restore_autonomy":
            if self._mode == AutonomyMode.FUSED and confirmation_token != "manual-confirmed":
                raise ValueError("Fused mode restore requires confirmation_token='manual-confirmed'")
            return AutonomyMode.AUTONOMOUS
        raise ValueError(f"Unsupported supervision intervention action: {action}")


_HUB: SupervisionHub | None = None


def get_supervision_hub() -> SupervisionHub:
    global _HUB
    if _HUB is None:
        _HUB = SupervisionHub()
    return _HUB
