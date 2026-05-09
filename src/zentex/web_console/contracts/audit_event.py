from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str
    session_id: str
    turn_id: str
    entry_type: str
    timestamp: str
    source: Optional[str] = "kernel"
    trace_id: Optional[str] = None
    context_info: Dict[str, Any] = Field(default_factory=dict)
    payload: Any
