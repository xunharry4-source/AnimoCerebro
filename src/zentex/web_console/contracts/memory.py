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
    health_status: str = "unknown"
    projection_failures: List[Any] = Field(default_factory=list)
    initialization_failures: List[Any] = Field(default_factory=list)
    governance_failures: List[Any] = Field(default_factory=list)
    package_imports: int = 0
    contamination_events: int = 0
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


class MemoryBlockDescriptorItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    block_id: str
    block_kind: str
    required: bool = False
    derived: bool = False
    codec_chain: List[str] = Field(default_factory=list)
    content_checksum: str = ""
    storage_checksum: str = ""
    status: str = "unknown"
    repairable: bool = True
    encryption_context: Optional[str] = None
    compression_strategy: str = "none"
    serializer_version: str = ""
    last_verified_at: Optional[datetime] = None


class MemoryRecordManifestItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: str
    manifest_version: int = 1
    descriptors: List[MemoryBlockDescriptorItem] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class MemoryRepairTicketItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: str
    record_health_status: str = "unknown"
    repaired_blocks: List[str] = Field(default_factory=list)
    quarantined_blocks: List[str] = Field(default_factory=list)
    projection_repairs: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class MemoryRecordDiagnosticsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    memory_id: str
    storage_schema_version: int = 1
    record_health_status: str = "unknown"
    repair_status: str = "unknown"
    header: Dict[str, Any] = Field(default_factory=dict)
    manifest: Optional[MemoryRecordManifestItem] = None
    verification: Optional[MemoryRepairTicketItem] = None


class MemoryRepairSchedulerStatusPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    interval_seconds: int = 0
    last_cycle_at: Optional[str] = None
    last_summary: Dict[str, Any] = Field(default_factory=dict)


class MemoryRepairAllPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    triggered_by: str = "web_console"
    scheduler: MemoryRepairSchedulerStatusPayload
    items: List[MemoryRepairTicketItem] = Field(default_factory=list)


MemoryRecordDiagnosticsPayload.model_rebuild()
MemoryRepairAllPayload.model_rebuild()
EnhancedMemorySearchPayload.model_rebuild()
EnhancedMemoryAuditEventItem.model_rebuild()
EnhancedMemoryAuditPayload.model_rebuild()
EnhancedMemoryOverviewPayload.model_rebuild()
EnhancedMemoryRecordsPayload.model_rebuild()
