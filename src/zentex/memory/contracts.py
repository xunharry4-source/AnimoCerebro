from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class MemoryBackendStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: str
    package_name: str | None = None
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
    request_id: str | None = None
    source_event_id: str | None = None
    target_id: str | None = None
    version_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)
    status: str
    visibility: str
    trust_level: str
    management_note: str | None = None
    correction_note: str | None = None
    supersedes_memory_id: str | None = None
    superseded_by_memory_id: str | None = None
    operator: str
    last_action: str
    last_action_reason: str
    last_verified_at: datetime | None = None
    updated_at: datetime
    created_at: datetime
    
    compressed_by: str | None = None
    compression_summary: str | None = None
    is_tombstone: bool = False
    g38_audit_id: str | None = None
    
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
