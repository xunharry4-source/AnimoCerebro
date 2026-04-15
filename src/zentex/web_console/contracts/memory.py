from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field

# Re-exporting from core contracts
from zentex.memory.contracts import (
    MemoryBackendStatusItem,
    EnhancedMemoryRecordItem,
    EnhancedMemoryRecallHitItem
)

class MemoryStoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: Optional[str] = None
    layer: str = "semantic"
    source: str = "web_console_manual"
    trace_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MemoryRecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    limit: int = 10
    trace_id: Optional[str] = None
    target_id: Optional[str] = None


class UpdateEnhancedMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = None
    visibility: Optional[str] = None
    trust_level: Optional[str] = None
    management_note: Optional[str] = None
    correction_note: Optional[str] = None
    operator: str = "web_console"
    reason: str = "manual_update"
    supersedes_memory_id: Optional[str] = None
    superseded_by_memory_id: Optional[str] = None
    mark_verified: bool = False


class EnhancedMemoryAuditEventItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str
    memory_id: str
    action: str
    reason: str
    operator: str = "system"
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class EnhancedMemoryAuditPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: str
    limit: int
    items: List[EnhancedMemoryAuditEventItem] = Field(default_factory=list)


class EnhancedMemoryOverviewPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    semantic_count: int = 0
    procedural_count: int = 0
    episodic_count: int = 0
    active_count: int = 0
    deprecated_count: int = 0
    archived_count: int = 0
    suspect_count: int = 0
    projection_failures: List[Any] = Field(default_factory=list)
    backends: List[MemoryBackendStatusItem] = Field(default_factory=list)


class EnhancedMemoryRecordsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    layer: str
    limit: int
    items: List[EnhancedMemoryRecordItem] = Field(default_factory=list)


class EnhancedMemorySearchPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str
    limit: int
    trace_id: Optional[str] = None
    target_id: Optional[str] = None
    items: List[EnhancedMemoryRecallHitItem] = Field(default_factory=list)
