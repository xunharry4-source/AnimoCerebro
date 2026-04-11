from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field


class TranscriptEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str
    session_id: str
    turn_id: str
    entry_type: str
    timestamp: str
    source: str
    trace_id: str
    context_info: Dict[str, Any] = Field(default_factory=dict)
    payload: Any

