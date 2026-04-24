from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class MemoryBackendStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: str
    package_name: Optional[str] = None
    package_installed: bool
    write_enabled: bool
    recall_enabled: bool
    mode: str
    detail: str

class EnhancedMemoryRecordItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    memory_layer: str
    source_kind: str
    title: str
    summary: str
    content: str
    trace_id: str
    request_id: Optional[str] = None
    source_event_id: Optional[str] = None
    target_id: Optional[str] = None
    version_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)
    status: str
    visibility: str
    trust_level: str
    management_note: Optional[str] = None
    correction_note: Optional[str] = None
    supersedes_memory_id: Optional[str] = None
    superseded_by_memory_id: Optional[str] = None
    operator: str
    last_action: str
    last_action_reason: str
    last_verified_at: Optional[datetime] = None
    updated_at: datetime
    created_at: datetime
    
    compressed_by: Optional[str] = None
    compression_summary: Optional[str] = None
    is_tombstone: bool = False
    g38_audit_id: Optional[str] = None
    
    memory_tier: str = "hot"
    emotional_valence: str = "neutral"
    affect_intensity: float = 0.0
    content_hash: str = ""
    
    memory_kind: str = "collection"
    
    confidence_score: float = 0.5
    source_credibility: str = "direct_observation"
    verification_status: str = "unverified"
    contradiction_count: int = 0

class EnhancedMemoryRecallHitItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    memory_layer: str
    source_kind: str
    title: str
    summary: str
    trace_id: str
    score: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


MemoryBackendStatusItem.model_rebuild()
EnhancedMemoryRecordItem.model_rebuild()
EnhancedMemoryRecallHitItem.model_rebuild()
