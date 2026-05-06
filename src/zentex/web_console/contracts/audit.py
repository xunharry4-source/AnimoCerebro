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
    content: str = ""
    status: str = ""
    question_driver_refs: List[str] = Field(default_factory=list)
    context_info: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)


class AuditPagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: List[AuditRecordItem] = Field(default_factory=list)
    page: int
    page_size: int
    total_items: int
    total_pages: int


class AuditTraceStartsPagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: List[Dict[str, Any]] = Field(default_factory=list)
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


class AuditGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    title: str
    lane: str
    status: str
    description: str
    href: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


class AuditGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str
    source: str
    target: str
    label: str = ""


class AuditGraphLane(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lane_id: str
    title: str
    subtitle: str
    nodes: List[AuditGraphNode] = Field(default_factory=list)


class AuditGraphPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str
    title: str
    subtitle: str
    database_backed: bool = True
    generated_at: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    lanes: List[AuditGraphLane] = Field(default_factory=list)
    edges: List[AuditGraphEdge] = Field(default_factory=list)


AuditGraphLane.model_rebuild()
AuditGraphPayload.model_rebuild()
TurnAuditItem.model_rebuild()
