from __future__ import annotations
from typing import List, Optional


from pydantic import BaseModel, ConfigDict, Field

from zentex.web_console.contracts.transcript import TranscriptEventPayload


class TranscriptReplayPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    trace_id: str
    summary: str
    source_module: Optional[str] = None
    invocation_phase: Optional[str] = None
    question_driver_refs: List[str] = Field(default_factory=list)
    events: List[TranscriptEventPayload] = Field(default_factory=list)


class TurnReplayTraceGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str
    label: str
    entry_count: int = 0


class TurnReplayPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    turn_id: str
    trace_id: str
    summary: str
    trace_groups: List[TurnReplayTraceGroup] = Field(default_factory=list)
    events: List[TranscriptEventPayload] = Field(default_factory=list)

