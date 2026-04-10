from __future__ import annotations

"""Web-console contracts for enhanced memory inspection and recall."""

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
    
    # Sub-function 59.5 - Reference Chain & Compression fields
    compressed_by: str | None = None
    compression_summary: str | None = None
    is_tombstone: bool = False
    g38_audit_id: str | None = None
    
    # Classification axes (G39 three-tier + affect signal)
    memory_tier: str = "hot"
    emotional_valence: str = "neutral"
    affect_intensity: float = 0.0
    content_hash: str = ""
    
    # Storage mode
    memory_kind: str = "collection"
    
    # Confidence & uncertainty modeling
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


class EnhancedMemoryOverviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    semantic_count: int = Field(ge=0)
    procedural_count: int = Field(ge=0)
    episodic_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    deprecated_count: int = Field(ge=0)
    archived_count: int = Field(ge=0)
    suspect_count: int = Field(ge=0)
    projection_failures: list[str] = Field(default_factory=list)
    backends: list[MemoryBackendStatusItem] = Field(default_factory=list)


class EnhancedMemoryRecordsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: str
    limit: int = Field(ge=1)
    items: list[EnhancedMemoryRecordItem] = Field(default_factory=list)


class EnhancedMemorySearchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    limit: int = Field(ge=1)
    trace_id: str | None = None
    target_id: str | None = None
    items: list[EnhancedMemoryRecallHitItem] = Field(default_factory=list)


class EnhancedMemoryAuditEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    memory_id: str
    action: str
    reason: str
    operator: str
    details: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class EnhancedMemoryAuditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    limit: int = Field(ge=1)
    items: list[EnhancedMemoryAuditEventItem] = Field(default_factory=list)


class UpdateEnhancedMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    visibility: str | None = None
    trust_level: str | None = None
    management_note: str | None = None
    correction_note: str | None = None
    supersedes_memory_id: str | None = None
    superseded_by_memory_id: str | None = None
    operator: str = "operator"
    reason: str = "Memory governance updated."
    mark_verified: bool = False
