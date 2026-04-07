from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditRecordItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str
    trace_id: str
    session_id: str
    turn_id: str
    entry_type: str
    timestamp: str
    source: str
    summary: str
    question_driver_refs: List[str] = Field(default_factory=list)
    context_info: Dict[str, Any] = Field(default_factory=dict)


class AuditPagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: List[AuditRecordItem] = Field(default_factory=list)
    page: int
    page_size: int
    total_items: int
    total_pages: int


class TurnToolSummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str
    behavior_key: str
    invocation_id: Optional[str] = None
    trace_id: str
    summary: str


class TurnAuditItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: str
    session_id: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str
    goal_titles: List[str] = Field(default_factory=list)
    tool_summaries: List[TurnToolSummaryItem] = Field(default_factory=list)


class TurnAuditPagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: List[TurnAuditItem] = Field(default_factory=list)
    page: int
    page_size: int
    total_items: int
    total_pages: int

