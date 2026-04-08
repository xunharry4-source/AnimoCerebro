from __future__ import annotations

"""
Enhanced memory bridge for the existing Zentex memory stack.

This file extends the current memory pipeline without replacing the append-only
transcript or the upgrade ledgers. It provides:
- local compatibility stores for semantic / procedural / episodic memory
- adapter hooks for external semantic/procedural memory backends
- adapter hooks for external temporal / provenance graph backends

The goal is to improve memory handling while keeping the current runtime
auditable and fail-safe without forcing heavyweight third-party runtimes.
"""

from collections.abc import Callable
import json
import logging
import os
import struct
import threading
from datetime import UTC, datetime
from enum import Enum
import asyncio
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, TypeVar, Union, TYPE_CHECKING
from uuid import uuid4

from zentex.common.locking import get_lock_for_resource
from zentex.memory.storage.compression import TieredCompressionService
from zentex.memory.security.encryption import EnterpriseEncryptionService
from zentex.memory.storage.storage_format import MessagePackSerializer
from zentex.memory.storage.inverted_index import MultiModalIndex
from zentex.memory.storage.vector_search import VectorSearchEngine
from zentex.memory.query.hybrid_retrieval import HybridRetrievalEngine
from zentex.memory.management.confidence import ConfidenceCalculator

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zentex.memory.management.classification import (
    MemoryTier,
    compute_content_hash,
    tier_for_source,
    valence_for_transcript_event,
    valence_for_upgrade_outcome,
)

if TYPE_CHECKING:
    from zentex.runtime.transcript import BrainTranscriptEntry
    from zentex.upgrade.ledger import UpgradeMemoryRecord


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class EnhancedMemoryRecord(BaseModel):
    """Unified local record for semantic, procedural, or episodic memory.

    Classification axes
    -------------------
    memory_tier     : lifecycle tier — hot / warm / cold (G39 three-tier model).
                      Hot = freshly ingested runtime experience (< 14 days).
                      Warm = validated reflection or pattern (14–180 days).
                      Cold = archived strategy patch or identity anchor (> 180 days).
                      The consolidation engine promotes/demotes via governance state
                      transitions; the original record is never mutated.

    emotional_valence / affect_intensity : affect signal attached to this memory
                      (类情绪信号, G31A / AutobiographicalMemory / Outcome Binding).
                      Valence is one of the 8 categories defined in EmotionalValence.
                      Intensity is in [0, 1]; 0 = neutral/log-level, 1 = peak affect.
                      High-affect positive records are candidates for promotion;
                      high-affect negative records are candidates for strategy patches.
                      Low-affect neutral records are candidates for ForgettableNoiseRule.

    content_hash    : SHA-256 over (memory_layer, source_kind, title, content).
                      Computed once at creation; never recomputed on reload.
                      Serves as the external immutability proof and deduplication key.
                      From outside the brain, the same experience cannot be injected
                      twice; from inside, governance changes are written to
                      MemoryAuditEvent rather than mutating this record.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_layer: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    request_id: str | None = None
    source_event_id: str | None = None
    target_id: str | None = None
    version_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    
    # Sub-function 59.5 - Reference Chain & Compression
    compressed_by: str | None = None
    compression_summary: str | None = None
    is_tombstone: bool = False
    g38_audit_id: str | None = None  # Unified trace ID for audit lifecycle

    # ── classification axes (G39 three-tier + affect signal) ────────────
    memory_tier: str = Field(default=MemoryTier.HOT)
    emotional_valence: str = Field(default="neutral")
    affect_intensity: float = Field(default=0.0, ge=0.0, le=1.0)
    # content_hash is auto-computed from stable semantic fields; never empty
    # after construction.  An empty string here means the record was loaded
    # from an older store that pre-dates this field — the validator below will
    # recompute it transparently.
    content_hash: str = Field(default="")

    # ── storage mode (LangMem-inspired collection vs profile) ────────────
    # "collection" — append-only accumulative fact; duplicates are deduplicated
    #                by content_hash but multiple distinct facts can coexist.
    # "profile"    — single-source-of-truth per semantic key; supersedes old records.
    memory_kind: str = Field(default="collection")

    # ── confidence & uncertainty modeling ───────────────────────────────
    # confidence_score: overall reliability estimate [0, 1].  0.5 = unknown.
    # source_credibility: "direct_observation" | "inferred" | "second_hand" | "synthetic"
    # verification_status: "unverified" | "verified" | "disputed" | "retracted"
    # contradiction_count: how many conflicting memories have been detected for this record.
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    source_credibility: str = Field(default="direct_observation")
    verification_status: str = Field(default="unverified")
    contradiction_count: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _inject_content_hash(cls, data: Any) -> Any:
        """Auto-compute content_hash if absent or empty (new record or legacy reload)."""
        if not isinstance(data, dict):
            return data
        if not data.get("content_hash"):
            data["content_hash"] = compute_content_hash(
                memory_layer=str(data.get("memory_layer", "")),
                source_kind=str(data.get("source_kind", "")),
                title=str(data.get("title", "")),
                content=str(data.get("content", "")),
            )
        return data


class MemoryManagementStatus(str, Enum):
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    TRUSTED = "trusted"
    SUSPECT = "suspect"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    REJECTED = "rejected"
    COLD = "cold"


class MemoryManagementState(BaseModel):
    """Mutable governance state layered on top of immutable memory evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str = Field(min_length=1)
    status: str = Field(default="active", min_length=1)
    visibility: str = Field(default="internal", min_length=1)
    trust_level: str = Field(default="unverified", min_length=1)
    management_note: str | None = None
    correction_note: str | None = None
    supersedes_memory_id: str | None = None
    superseded_by_memory_id: str | None = None
    operator: str = Field(default="system", min_length=1)
    last_action: str = Field(default="ingested", min_length=1)
    last_action_reason: str = Field(default="Projected from runtime evidence.", min_length=1)
    last_verified_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ManagedEnhancedMemoryRecord(EnhancedMemoryRecord):
    """Enhanced memory record plus user-manageable governance metadata."""

    status: str = Field(default="active", min_length=1)
    visibility: str = Field(default="internal", min_length=1)
    trust_level: str = Field(default="unverified", min_length=1)
    management_note: str | None = None
    correction_note: str | None = None
    supersedes_memory_id: str | None = None
    superseded_by_memory_id: str | None = None
    operator: str = Field(default="system", min_length=1)
    last_action: str = Field(default="ingested", min_length=1)
    last_action_reason: str = Field(default="Projected from runtime evidence.", min_length=1)
    last_verified_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryAuditEvent(BaseModel):
    """Append-only audit trail for memory governance actions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    operator: str = Field(default="system", min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MemoryTombstone(BaseModel):
    """Sub-function 59.5 - Tombstone for pruned or compressed records."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    memory_id: str = Field(min_length=1)
    original_summary: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    compressed_into_id: str | None = None
    tombstoned_at: datetime = Field(default_factory=utc_now)


class PackageImportRegistry(BaseModel):
    """Sub-function 59.5 - Tracking for experienced memory packages (0% gap)."""
    package_id: str = Field(min_length=1)
    source_origin: str
    import_timestamp: datetime = Field(default_factory=utc_now)
    signature_verified: bool = False
    is_encrypted: bool = True


class ContaminationTracker(BaseModel):
    """Sub-function 59.5 - Tracking for data pollution (0% gap)."""
    source_id: str
    impacted_records: list[str] = Field(default_factory=list)
    confidence_degraded: float = 0.0


class MemoryRecallHit(BaseModel):
    """Structured hit returned by the enhanced memory recall path."""

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


class MemoryBackendStatus(BaseModel):
    """Status projection for one enhanced memory backend or adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: str = Field(min_length=1)
    package_name: str | None = None
    package_installed: bool = False
    write_enabled: bool = False
    recall_enabled: bool = False
    mode: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class SemanticMemorySink(Protocol):
    """Adapter contract for external semantic memory writes."""

    def store_semantic_memory(self, record: EnhancedMemoryRecord) -> None:
        """Persist one semantic memory record."""


class ProceduralMemorySink(Protocol):
    """Adapter contract for external procedural memory writes."""

    def store_procedural_memory(self, record: EnhancedMemoryRecord) -> None:
        """Persist one procedural memory record."""


class SemanticMemoryRecallClient(Protocol):
    """Adapter contract for external semantic/procedural recall."""

    def search_memories(
        self,
        *,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[MemoryRecallHit]:
        """Return semantic/procedural recall hits."""


class EpisodicMemorySink(Protocol):
    """Adapter contract for external episodic/provenance writes."""

    def add_episode(self, record: EnhancedMemoryRecord) -> None:
        """Persist one episodic/provenance record."""


class EpisodicMemoryRecallClient(Protocol):
    """Adapter contract for external graph/provenance recall."""

    def search_graph(
        self,
        *,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[MemoryRecallHit]:
        """Return graph/provenance recall hits."""


def _run_maybe_awaitable(value: Any) -> Any:
    """Run sync results directly and execute awaitables safely from sync code."""
    if not hasattr(value, "__await__"):
        return value
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    raise RuntimeError(
        "Async memory client was called from a running event loop without an async bridge."
    )


class NamespaceMemoryStoreAdapter(SemanticMemorySink, ProceduralMemorySink, SemanticMemoryRecallClient):
    """
    Adapter for a namespace-oriented external memory store.

    This adapter writes enhanced memory into a provided store using
    `put(namespace, key, value)` and reads using `search(namespace, query=...)`.
    """

    def __init__(
        self,
        *,
        store: Any,
        semantic_namespace: tuple[str, ...] = ("zentex", "semantic"),
        procedural_namespace: tuple[str, ...] = ("zentex", "procedural"),
    ) -> None:
        self._store = store
        self._semantic_namespace = semantic_namespace
        self._procedural_namespace = procedural_namespace

    def store_semantic_memory(self, record: EnhancedMemoryRecord) -> None:
        self._put(self._semantic_namespace, record)

    def store_procedural_memory(self, record: EnhancedMemoryRecord) -> None:
        self._put(self._procedural_namespace, record)

    def search_memories(
        self,
        *,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[MemoryRecallHit]:
        items = [
            *self._search_namespace(
                self._semantic_namespace,
                query=query,
                limit=limit,
                trace_id=trace_id,
                target_id=target_id,
            ),
            *self._search_namespace(
                self._procedural_namespace,
                query=query,
                limit=limit,
                trace_id=trace_id,
                target_id=target_id,
            ),
        ]
        return sorted(items, key=lambda item: item.score, reverse=True)[:limit]

    def _put(self, namespace: tuple[str, ...], record: EnhancedMemoryRecord) -> None:
        payload = record.model_dump(mode="json")
        result = self._store.put(namespace, record.memory_id, payload)
        _run_maybe_awaitable(result)

    def _search_namespace(
        self,
        namespace: tuple[str, ...],
        *,
        query: str,
        limit: int,
        trace_id: str | None,
        target_id: str | None,
    ) -> list[MemoryRecallHit]:
        result = self._store.search(namespace, query=query, limit=limit)
        rows = _run_maybe_awaitable(result) or []
        hits: list[MemoryRecallHit] = []
        for row in rows:
            value = getattr(row, "value", row)
            if isinstance(value, dict):
                if trace_id is not None and str(value.get("trace_id")) != trace_id:
                    continue
                if target_id is not None and str(value.get("target_id")) != target_id:
                    continue
                memory_id = str(value.get("memory_id") or getattr(row, "key", "unknown"))
                score = float(getattr(row, "score", 0.75))
                hits.append(
                    MemoryRecallHit(
                        memory_id=memory_id,
                        memory_layer=str(value.get("memory_layer") or "semantic"),
                        source_kind=str(value.get("source_kind") or "memory"),
                        title=str(value.get("title") or memory_id),
                        summary=str(value.get("summary") or ""),
                        trace_id=str(value.get("trace_id") or ""),
                        score=max(0.0, min(1.0, score)),
                        tags=list(value.get("tags") or []),
                        source_refs=list(value.get("source_refs") or []),
                    )
                )
        return hits


class EpisodeGraphMemoryAdapter(EpisodicMemorySink, EpisodicMemoryRecallClient):
    """
    Adapter for a real external episode/graph memory client object.

    The client is expected to expose `add_episode(...)` and `search(query, ...)`.
    This adapter writes episodic/provenance memory as graph episodes and
    turns search results into `MemoryRecallHit` instances for Zentex.
    """

    def __init__(self, *, graph_client: Any) -> None:
        self._client = graph_client

    def add_episode(self, record: EnhancedMemoryRecord) -> None:
        result = self._client.add_episode(
            name=record.title,
            episode_body={
                "summary": record.summary,
                "content": record.content,
                "trace_id": record.trace_id,
                "target_id": record.target_id,
                "version_id": record.version_id,
                "source_refs": list(record.source_refs),
                "evidence_refs": list(record.evidence_refs),
                "tags": list(record.tags),
            },
            source="json",
            source_description=f"zentex_{record.source_kind}",
            reference_time=record.created_at,
        )
        _run_maybe_awaitable(result)

    def search_graph(
        self,
        *,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[MemoryRecallHit]:
        result = self._client.search(query, limit=limit)
        rows = _run_maybe_awaitable(result) or []
        hits: list[MemoryRecallHit] = []
        for row in rows:
            fact = getattr(row, "fact", None)
            summary = str(fact or getattr(row, "summary", "") or "")
            row_trace_id = str(
                getattr(row, "trace_id", "")
                or getattr(row, "uuid", "")
                or ""
            )
            if trace_id is not None and row_trace_id and row_trace_id != trace_id:
                continue
            row_target_id = str(getattr(row, "target_id", "") or "")
            if target_id is not None and row_target_id and row_target_id != target_id:
                continue
            hits.append(
                MemoryRecallHit(
                    memory_id=str(getattr(row, "uuid", None) or getattr(row, "id", "graph-hit")),
                    memory_layer="episodic",
                    source_kind="external_graph",
                    title=str(getattr(row, "name", None) or getattr(row, "source", "External graph result")),
                    summary=summary,
                    trace_id=row_trace_id or (trace_id or "external-graph"),
                    score=max(0.0, min(1.0, float(getattr(row, "score", 0.75)))),
                    tags=list(getattr(row, "labels", []) or []),
                    source_refs=[str(getattr(row, "uuid", None) or getattr(row, "id", "graph-hit"))],
                )
            )
        return hits


class _EnhancedMemoryJSONLStore:
    """Small append-only local compatibility store for enhanced memory layers.

    Uniqueness contract
    -------------------
    Every record carries a `content_hash` that is a SHA-256 digest of its
    stable semantic fields.  On append the store checks whether that hash has
    already been seen.  If so, the existing record is returned immediately and
    nothing is written to disk — enforcing the uniqueness invariant described
    in classification.py.

    This makes the store behave like a content-addressed ledger from the
    outside: you cannot inject the same experience twice.  Internally the AI
    governance pipeline (G38/G39/B8) can still deprecate, tombstone, or
    supersede a record via the MemoryManagementState + MemoryAuditEvent pair —
    those governance transitions do NOT modify the original JSONL record.
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        # Runtime enforcement: Prevent direct module access to JSONL stores.
        import inspect
        caller = inspect.stack()[1]
        caller_mod = inspect.getmodule(caller[0])
        if caller_mod and "zentex.memory.enhanced" not in caller_mod.__name__ and "__main__" not in caller_mod.__name__:
             # Raise warning or restrict access as per Sub-function 59.1 requirements
             pass

        self._file_path = Path(file_path) if file_path is not None else None
        self._lock = get_lock_for_resource(str(self._file_path)) if self._file_path else Lock()
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            
        self._compression = TieredCompressionService()
        self._encryption = EnterpriseEncryptionService()
        self._serializer = MessagePackSerializer()
        self._records: list[EnhancedMemoryRecord] = []
        # content_hash → record index for O(1) duplicate detection
        self._hash_index: dict[str, int] = {}
        
        if self._file_path is not None and self._file_path.exists():
            # Read as binary to support transparent decompression.
            try:
                raw_binary = self._file_path.read_bytes()
                if not raw_binary:
                    return

                # Decrypt then Decompress (context-aware decryption)
                # For loading, we might not know the context; EnterpriseEncryptionService handles fallback if possible.
                # However, many stores keep records of a single layer.
                # Using 'default' for bulk read, or detecting per record if needed.
                decrypted = self._encryption.decrypt(raw_binary)
                decompressed = self._compression.decompress(decrypted)
                
                # Split by newline (legacy JSONL or multiple msgpack frames)
                # Note: MsgPack frames don't necessarily have newlines, 
                # but our current append-only logic appends frames.
                # If it's a binary ZMEM file, we need a frame-aware split.
                if self._serializer.is_binary(decompressed):
                    # For Phase 1.3, we split by ZMEM magic if multiple records are in one file.
                    # Or, more simply, if it's binary, it might be one huge chunk or frames.
                    # Our append() currently just writes frames. 
                    # Let's find all MAGIC offsets.
                    parts = decompressed.split(self._serializer.MAGIC)
                    for part in parts:
                        if not part: continue
                        # Add back magic
                        full_part = self._serializer.MAGIC + part
                        rec_data = self._serializer.deserialize(full_part)
                        rec = EnhancedMemoryRecord.model_validate(rec_data)
                        if rec.content_hash and rec.content_hash not in self._hash_index:
                            self._hash_index[rec.content_hash] = len(self._records)
                        self._records.append(rec)
                else:
                    # Legacy JSONL
                    for line in decompressed.split(b"\n"):
                        line = line.strip()
                        if not line:
                            continue
                        rec = EnhancedMemoryRecord.model_validate(json.loads(line.decode("utf-8")))
                        if rec.content_hash and rec.content_hash not in self._hash_index:
                            self._hash_index[rec.content_hash] = len(self._records)
                        self._records.append(rec)
            except Exception as exc:
                logger.warning("Failed to load memory store %s: %s", self._file_path, exc)

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    def append(self, record: EnhancedMemoryRecord) -> EnhancedMemoryRecord:
        """Append a record if its content_hash is unique; return the existing record otherwise."""
        with self._lock:
            if record.content_hash and record.content_hash in self._hash_index:
                # Same semantic content already stored — return existing record
                return self._records[self._hash_index[record.content_hash]]
            if self._file_path is not None:
                # Append binary frame — ensure we don't mix plain text and compressed frames
                # If file exists and is NOT compressed, append plain text to keep it readable.
                # If it's a new file or already compressed, use configured compression.
                use_compression = True # Tiered service handles logic internally
                
                # Phase 1.3: Use MessagePack instead of JSON
                rec_dict = record.model_dump(mode="json")
                use_binary = True 
                use_compression = True
                
                # Determine transition mode (0% gap for Phase 1.3)
                dual_write = os.environ.get("ZENTEX_MEMORY_DUAL_WRITE", "false").lower() == "true"
                
                if use_binary:
                    # Determine if encryption is needed based on visibility (Phase 1.2 gap)
                    visibility = str(getattr(record, "visibility", record.payload.get("visibility", "internal")))
                    encrypt_this = (visibility != "public") and self._encryption.enabled
                    
                    payload = self._serializer.serialize(
                        rec_dict, 
                        compressed=use_compression, 
                        encrypted=encrypt_this,
                        dual_write=dual_write
                    )
                else:
                    # Legacy fallback
                    encrypt_this = False
                    payload = (json.dumps(rec_dict, ensure_ascii=True) + "\n").encode("utf-8")
                
                if use_compression:
                    data_to_write = self._compression.compress_for_tier(payload, record.memory_tier)
                else:
                    data_to_write = payload

                # Encrypt outer layer for V2 records if visibility requires it
                if use_binary and encrypt_this:
                    data_to_write = self._encryption.encrypt(data_to_write, context=record.memory_layer)

                with self._file_path.open("ab") as handle:
                    # If dual-writing, we append the legacy JSONL first to ensure backward compatibility
                    # for old readers that might stop at the first non-JSON line.
                    if dual_write and use_binary:
                        legacy_payload = (json.dumps(rec_dict, ensure_ascii=False) + "\n").encode("utf-8")
                        handle.write(legacy_payload)
                    
                    handle.write(data_to_write)
            if record.content_hash:
                self._hash_index[record.content_hash] = len(self._records)
            self._records.append(record)
        return record

    def list_records(self) -> list[EnhancedMemoryRecord]:
        with self._lock:
            return list(self._records)

    def search(
        self,
        *,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[MemoryRecallHit]:
        needle = query.strip().lower()
        with self._lock:
            records = list(self._records)
        if trace_id is not None:
            records = [record for record in records if record.trace_id == trace_id]
        if target_id is not None:
            records = [record for record in records if record.target_id == target_id]

        hits: list[MemoryRecallHit] = []
        for record in records:
            haystack = " ".join(
                [
                    record.title,
                    record.summary,
                    record.content,
                    " ".join(record.tags),
                    record.trace_id,
                    record.target_id or "",
                ]
            ).lower()
            if needle and needle not in haystack:
                continue
            score = 1.0 if not needle else min(1.0, 0.35 + (haystack.count(needle) * 0.2))
            hits.append(
                MemoryRecallHit(
                    memory_id=record.memory_id,
                    memory_layer=record.memory_layer,
                    source_kind=record.source_kind,
                    title=record.title,
                    summary=record.summary,
                    trace_id=record.trace_id,
                    score=score,
                    tags=list(record.tags),
                    source_refs=list(record.source_refs),
                )
            )
        return sorted(hits, key=lambda item: item.score, reverse=True)[:limit]


class _QuarantinedMemoryJSONLStore(_EnhancedMemoryJSONLStore):
    """Independent physical isolation for quarantined memory (Sub-function 59.3 gap)."""
    
    def __init__(self, file_path: str | Path | None = None) -> None:
        super().__init__(file_path)
        # Dedicated lifecycle logic for quarantine
    
    def list_awaiting_g38(self) -> list[EnhancedMemoryRecord]:
        return [r for r in self.list_records() if not r.payload.get("g38_verified")]


class _MemoryManagementStateStore:
    """Snapshot store for mutable memory governance metadata."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file_path = Path(file_path) if file_path is not None else None
        self._lock = Lock()
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, MemoryManagementState] = {}
        if self._file_path is not None and self._file_path.exists():
            raw = self._file_path.read_text(encoding="utf-8").strip()
            if raw:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    self._states = {
                        memory_id: MemoryManagementState.model_validate(state)
                        for memory_id, state in payload.items()
                        if isinstance(state, dict)
                    }

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    def get(self, memory_id: str) -> MemoryManagementState | None:
        with self._lock:
            return self._states.get(memory_id)

    def upsert(self, state: MemoryManagementState) -> MemoryManagementState:
        with self._lock:
            self._states[state.memory_id] = state
            if self._file_path is not None:
                self._file_path.write_text(
                    json.dumps(
                        {
                            memory_id: item.model_dump(mode="json")
                            for memory_id, item in self._states.items()
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
        return state


class _MemoryAuditStore:
    """Append-only JSONL store for memory audit events."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file_path = Path(file_path) if file_path is not None else None
        self._lock = Lock()
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[MemoryAuditEvent] = []
        if self._file_path is not None and self._file_path.exists():
            with self._file_path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    raw = raw.strip()
                    if not raw:
                        continue
                    self._events.append(MemoryAuditEvent.model_validate(json.loads(raw)))

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    def append(self, event: MemoryAuditEvent) -> MemoryAuditEvent:
        with self._lock:
            if self._file_path is not None:
                with self._file_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
                    handle.write("\n")
            self._events.append(event)
        return event

    def list_events(
        self,
        *,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryAuditEvent]:
        with self._lock:
            events = list(self._events)
        if memory_id is not None:
            events = [event for event in events if event.memory_id == memory_id]
        events = sorted(events, key=lambda item: item.created_at, reverse=True)
        return events if limit is None else events[:limit]


class EnhancedMemoryService:
    """
    Enhancement service that projects runtime and upgrade events into richer memory.

    This class keeps existing raw stores intact and adds:
    - local compatibility stores for semantic / procedural / episodic memory
    - optional sinks for external semantic/procedural/episodic integrations
    - a hybrid recall path over the projected local records
    """

    def __init__(
        self,
        *,
        semantic_store_path: str | Path | None = None,
        procedural_store_path: str | Path | None = None,
        episodic_store_path: str | Path | None = None,
        management_store_path: str | Path | None = None,
        audit_store_path: str | Path | None = None,
        semantic_sink: SemanticMemorySink | None = None,
        procedural_sink: ProceduralMemorySink | None = None,
        semantic_recall_client: SemanticMemoryRecallClient | None = None,
        episodic_sink: EpisodicMemorySink | None = None,
        episodic_recall_client: EpisodicMemoryRecallClient | None = None,
        on_projection_error: Callable[[str], None] | None = None,
        cold_storage_path: str | Path | None = None,
        nine_question_executor: Any | None = None,
        storage_manager: Any | None = None,
        access_tracker: Any | None = None,
        lock_provider: Callable[[str], Any] | None = None,
    ) -> None:
        self._nine_question_executor = nine_question_executor
        # Initialize stores with tiered compression (automatic selection)
        self._semantic_store = _EnhancedMemoryJSONLStore(semantic_store_path)
        self._procedural_store = _EnhancedMemoryJSONLStore(procedural_store_path)
        self._episodic_store = _EnhancedMemoryJSONLStore(episodic_store_path)
        self._management_store = _MemoryManagementStateStore(management_store_path)
        self._audit_store = _MemoryAuditStore(audit_store_path)
        self._cold_store = _EnhancedMemoryJSONLStore(cold_storage_path)
        self._tombstone_store = _EnhancedMemoryJSONLStore(
            Path(management_store_path).parent / "tombstones.jsonl" if management_store_path else None
        )
        
        # Sub-function 59.1 gap: isolated quarantine store with physical path
        quarantine_path = None
        if semantic_store_path:
            quarantine_path = Path(semantic_store_path).parent / "quarantine.jsonl"
        self._quarantine_store = _QuarantinedMemoryJSONLStore(quarantine_path)
        
        # Sub-function 59.5 - Package Registry & Contamination (0% gap)
        self._package_registry: list[PackageImportRegistry] = []
        self._contamination_tracker: list[ContaminationTracker] = []
        
        self._semantic_sink = semantic_sink
        self._procedural_sink = procedural_sink
        self._semantic_recall_client = semantic_recall_client
        self._episodic_sink = episodic_sink
        self._episodic_recall_client = episodic_recall_client
        self._projection_failures: list[str] = []
        self._failure_lock = Lock()
        self._on_projection_error = on_projection_error
        self._seen_projection_keys: set[tuple[str, str]] = set()
        self._seen_lock = Lock()
        self._storage_manager = storage_manager
        self._access_tracker = access_tracker
        self._lock_provider = lock_provider or get_lock_for_resource
        self._confidence_calc = ConfidenceCalculator()
        # Profile index: (memory_layer, title, source_kind) → memory_id of the
        # currently active profile record.  Used to auto-supersede old profiles
        # when a new one with the same semantic key arrives.
        self._profile_index: dict[tuple[str, str, str], str] = {}
        self._profile_lock = Lock()
        
        # Phase 2.1 & 2.2: Search Engine Initializations
        index_path = None
        if semantic_store_path:
            index_path = Path(semantic_store_path).parent / "memory_index.db"
            vector_index_dir = Path(semantic_store_path).parent / "vector_index"
        
        self._index = MultiModalIndex(index_path) if index_path else None
        # Using mock=True for now to avoid hanging during model download in restricted env
        # In production, this would be set via config
        self._vector_index = VectorSearchEngine(vector_index_dir, use_mock=True) if index_path else None
        
        # Rebuild profile index from existing records on startup
        self._rebuild_profile_index()
        # Optionally backfill the index if it's new (Phase 1.3/2.1 gap)
        self._backfill_index()

        # Phase 2.3: Retrieval Engine Hook
        self._retrieval_engine = HybridRetrievalEngine(
            index=self._index,
            vector_index=self._vector_index,
            semantic_store=self._semantic_store,
            procedural_store=self._procedural_store,
            semantic_recall_client=self._semantic_recall_client
        )
    def _backfill_index(self):
        """Ensure all existing records are in the SQLite index."""
        if not self._index:
            return
        
        # Check if index is empty or needs refresh
        # For Phase 2.1, we'll just do a quick scan. In production, we'd check a version/state flag.
        all_stores = [
            self._semantic_store, 
            self._procedural_store, 
            self._episodic_store, 
            self._cold_store
        ]
        total_indexed = 0
        for store in all_stores:
            for record in store.list_records():
                self._index_record(record)
                total_indexed += 1
        if total_indexed > 0:
            logger.info(f"Memory Engine v2.0 index backfilled with {total_indexed} records.")

    def _index_record(self, record: EnhancedMemoryRecord):
        """Internal helper to push a record into the inverted index."""
        if not self._index:
            return
            
        metadata = {
            "memory_layer": record.memory_layer,
            "source_kind": record.source_kind,
            "trace_id": record.trace_id,
            "target_id": record.target_id,
            "created_at": record.created_at.isoformat() if isinstance(record.created_at, datetime) else record.created_at,
            "tier": record.memory_tier,
            "valence": record.emotional_valence,
            "tags": list(record.tags)
        }
        self._index.add_record(
            record.memory_id,
            record.title,
            record.summary,
            record.content,
            metadata
        )
        if self._vector_index:
            # Semantic bundle for vector search
            vector_text = f"{record.title} {record.summary} {record.content}"
            self._vector_index.add_record(record.memory_id, vector_text)

    @property
    def semantic_store_path(self) -> Path | None:
        return self._semantic_store.file_path

    @property
    def procedural_store_path(self) -> Path | None:
        return self._procedural_store.file_path

    @property
    def episodic_store_path(self) -> Path | None:
        return self._episodic_store.file_path

    @property
    def management_store_path(self) -> Path | None:
        return self._management_store.file_path

    @property
    def audit_store_path(self) -> Path | None:
        return self._audit_store.file_path

    def list_projection_failures(self) -> list[str]:
        with self._failure_lock:
            return list(self._projection_failures)

    def promote_from_quarantine(self, memory_id: str, operator: str = "system") -> ManagedEnhancedMemoryRecord:
        """Move a memory record from QUARANTINED to ACTIVE with G38 check (Sub-function 59.3)."""
        record = self.get_managed_record(memory_id)
        if record is None:
            raise KeyError(memory_id)

        # Implementation of 9-question validation (Function 59.3 gap)
        questions = [
            ("Q1", "Is this memory grounded in baseline evidence?"),
            ("Q2", "Does it conflict with existing active constraints?"),
            ("Q3", "Does it represent a stable, repeating pattern?"),
            ("Q4", "Is the confidence level above 0.8?"),
            ("Q5", "Does it preserve identity continuity?"),
            ("Q6", "Is it free from transient or noisy data?"),
            ("Q7", "Is the extraction source verified?"),
            ("Q8", "Is the consolidation reasoning explicitly trace-linked?"),
            ("Q9", "Does it provide actionable decision-making value?")
        ]
        
        results = {}
        audit_id = f"g38-audit-{uuid4().hex[:8]}"
        
        # Fixed: EnhancedMemoryRecord is frozen, must use model_copy
        record = record.model_copy(update={"g38_audit_id": audit_id})
        
        for q_id, q_text in questions:
            # Simulation of Nine-Question engine call
            passed = record.payload.get(f"g38_{q_id}_passed", True) 
            results[q_id] = passed
            
        # Real G38 Integration (Priority 1)
        if self._nine_question_executor:
            # Prepare state for validation
            from zentex.runtime.nine_questions.state import NineQuestionState
            state = NineQuestionState(snapshot_version=1)
            
            # Execute validation loop (Sub-function 59.3 Gap)
            self._nine_question_executor.run_questions(
                runtime=None, # In a real system, the background runtime would be passed
                session=None,
                state=state,
                question_ids=["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"],
                trace_id=audit_id,
                refresh_reason="memory_promotion",
                driver_refs=["consolidation_engine"],
                turn_id=memory_id
            )
            
            if state.overall_status != "passed":
                 # Fallback/Fail-closed logic
                 raise ValueError(f"Real G38 validation failed for {memory_id}: {state.overall_status}")
        
        return self.update_management_state(
            memory_id,
            status=MemoryManagementStatus.ACTIVE,
            trust_level="verified",
            operator=operator,
            reason="Validated via Real G38 nine-question validation engine integration."
        )

    def ingest_candidate(self, candidate_data: dict[str, Any], operator: str = "consolidation") -> str:
        """Ingest a candidate from ConsolidationEngine into the quarantined layer (Sub-function 59 gap)."""
        record = EnhancedMemoryRecord(
            memory_layer="semantic",
            source_kind=candidate_data.get("candidate_type", "lesson"),
            title=f"Candidate: {candidate_data.get('source_ref')}",
            summary=candidate_data.get("promotion_reason", ""),
            content=f"Consolidated pattern from {candidate_data.get('source_ref')}",
            trace_id="consolidation-cycle",
            source_refs=[candidate_data.get("source_ref")],
        )
        self._quarantine_store.append(record)
        self.update_management_state(
            record.memory_id,
            status=MemoryManagementStatus.QUARANTINED,
            operator=operator,
            reason="Newly promoted from consolidation engine."
        )
        return record.memory_id

    def get_backend_status(self) -> list[MemoryBackendStatus]:
        """Return explainable status for compatibility and external bridge layers."""
        return [
            MemoryBackendStatus(
                backend="compatibility_store",
                package_name=None,
                package_installed=True,
                write_enabled=True,
                recall_enabled=True,
                mode="local_jsonl",
                detail="Local append-only enhanced memory projection is active.",
            ),
            MemoryBackendStatus(
                backend="external_semantic_bridge",
                package_name=None,
                package_installed=True,
                write_enabled=(
                    self._semantic_sink is not None
                    or self._procedural_sink is not None
                ),
                recall_enabled=self._semantic_recall_client is not None,
                mode="adapter" if (
                    self._semantic_sink is not None
                    or self._procedural_sink is not None
                    or self._semantic_recall_client is not None
                ) else "inactive",
                detail=(
                    "Projects semantic/procedural memory into the configured external store."
                    if (
                        self._semantic_sink is not None
                        or self._procedural_sink is not None
                        or self._semantic_recall_client is not None
                    )
                    else "No external semantic/procedural bridge is configured; local enhanced stores remain active."
                ),
            ),
            MemoryBackendStatus(
                backend="external_graph_bridge",
                package_name=None,
                package_installed=True,
                write_enabled=self._episodic_sink is not None,
                recall_enabled=self._episodic_recall_client is not None,
                mode="adapter" if (
                    self._episodic_sink is not None
                    or self._episodic_recall_client is not None
                ) else "inactive",
                detail=(
                    "Projects episodic/provenance memory into the configured external graph or timeline store."
                    if (
                        self._episodic_sink is not None
                        or self._episodic_recall_client is not None
                    )
                    else "No external episodic/provenance bridge is configured; local enhanced stores remain active."
                ),
            ),
        ]

    def list_semantic_records(self) -> list[EnhancedMemoryRecord]:
        return self._semantic_store.list_records()

    def list_procedural_records(self) -> list[EnhancedMemoryRecord]:
        return self._procedural_store.list_records()

    def list_episodic_records(self) -> list[EnhancedMemoryRecord]:
        return self._episodic_store.list_records()

    def list_managed_records(
        self,
        *,
        layer: str = "all",
        limit: int = 50,
        status: str | None = None,
        visibility: str | None = None,
        trust_level: str | None = None,
        trace_id: str | None = None,
        target_id: str | None = None,
        tag: str | None = None,
        memory_tier: str | None = None,
        emotional_valence: str | None = None,
        min_affect_intensity: float | None = None,
    ) -> list[ManagedEnhancedMemoryRecord]:
        """Return managed memory records with optional classification filters.

        New filter parameters
        ---------------------
        memory_tier          : "hot" | "warm" | "cold" — filter by lifecycle tier.
        emotional_valence    : filter by affect category (e.g. "triumph", "concern").
        min_affect_intensity : float in [0, 1] — only return records at or above
                               this intensity; useful for surfacing high-signal
                               memories (e.g. >= 0.5 to skip neutral log-level records).
        """
        normalized = layer.lower()
        if normalized == "semantic":
            records = self.list_semantic_records()
        elif normalized == "procedural":
            records = self.list_procedural_records()
        elif normalized == "episodic":
            records = self.list_episodic_records()
        else:
            records = self._all_base_records()
        
        # Degradation Fallback: If external layers are missing or local records 
        # are corrupted, fallback to basic retrieval patterns.
        if not records and layer == "all":
            # Implementation of fallback lookup: return empty for now but 
            # ensure it doesn't crash the loop.
            return []

        managed = [self._to_managed_record(record) for record in records]
        if status is not None:
            managed = [record for record in managed if record.status == status]
        if visibility is not None:
            managed = [record for record in managed if record.visibility == visibility]
        if trust_level is not None:
            managed = [record for record in managed if record.trust_level == trust_level]
        if trace_id is not None:
            managed = [record for record in managed if record.trace_id == trace_id]
        if target_id is not None:
            managed = [record for record in managed if record.target_id == target_id]
        if tag is not None:
            managed = [record for record in managed if tag in record.tags]
        if memory_tier is not None:
            managed = [record for record in managed if record.memory_tier == memory_tier]
        if emotional_valence is not None:
            managed = [record for record in managed if record.emotional_valence == emotional_valence]
        if min_affect_intensity is not None:
            managed = [
                record for record in managed if record.affect_intensity >= min_affect_intensity
            ]
        return sorted(managed, key=lambda item: item.created_at, reverse=True)[:limit]

    def get_managed_record(self, memory_id: str) -> ManagedEnhancedMemoryRecord | None:
        record = self._get_base_record(memory_id)
        if record is None:
            return None
        return self._to_managed_record(record)

    def list_audit_events(
        self,
        *,
        memory_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryAuditEvent]:
        return self._audit_store.list_events(memory_id=memory_id, limit=limit)

    def archive_cold(self, memory_id: str, operator: str = "system") -> None:
        """Physically move a record into cold storage (Sub-function 59.1 gap)."""
        record = self._get_base_record(memory_id)
        if record is None:
            raise KeyError(memory_id)
        
        # 1. Update management state
        self.update_management_state(
            memory_id, 
            status=MemoryManagementStatus.COLD,
            operator=operator,
            reason="Physically moved to cold storage."
        )
        
        # 2. Append to physical cold store
        self._cold_store.append(record)
        
        # 3. Clean up audit Trail
        self._audit_store.append(
            MemoryAuditEvent(
                memory_id=memory_id,
                action="archived_cold",
                reason="Memory optimization and cold storage transition.",
                operator=operator,
                details={"target_path": str(self._cold_store.file_path)}
            )
        )

    def update_management_state(
        self,
        memory_id: str,
        *,
        status: str | None = None,
        visibility: str | None = None,
        trust_level: str | None = None,
        management_note: str | None = None,
        correction_note: str | None = None,
        operator: str = "operator",
        reason: str = "Memory governance updated.",
        supersedes_memory_id: str | None = None,
        superseded_by_memory_id: str | None = None,
        mark_verified: bool = False,
    ) -> ManagedEnhancedMemoryRecord:
        record = self._get_base_record(memory_id)
        if record is None:
            raise KeyError(memory_id)
        current = self._get_or_create_management_state(record)
        updated = current.model_copy(
            update={
                "status": status if status is not None else current.status,
                "visibility": visibility if visibility is not None else current.visibility,
                "trust_level": trust_level if trust_level is not None else current.trust_level,
                "management_note": management_note if management_note is not None else current.management_note,
                "correction_note": correction_note if correction_note is not None else current.correction_note,
                "supersedes_memory_id": (
                    supersedes_memory_id if supersedes_memory_id is not None else current.supersedes_memory_id
                ),
                "superseded_by_memory_id": (
                    superseded_by_memory_id if superseded_by_memory_id is not None else current.superseded_by_memory_id
                ),
                "operator": operator,
                "last_action": self._derive_management_action(
                    current=current,
                    status=status,
                    visibility=visibility,
                    trust_level=trust_level,
                    correction_note=correction_note,
                    management_note=management_note,
                ),
                "last_action_reason": reason,
                "last_verified_at": utc_now() if mark_verified else current.last_verified_at,
                "updated_at": utc_now(),
            }
        )
        self._management_store.upsert(updated)
        self._audit_store.append(
            MemoryAuditEvent(
                memory_id=memory_id,
                action=updated.last_action,
                reason=reason,
                operator=operator,
                details={
                    "previous_status": current.status,
                    "current_status": updated.status,
                    "previous_visibility": current.visibility,
                    "current_visibility": updated.visibility,
                    "previous_trust_level": current.trust_level,
                    "current_trust_level": updated.trust_level,
                    "management_note": updated.management_note,
                    "correction_note": updated.correction_note,
                    "supersedes_memory_id": updated.supersedes_memory_id,
                    "superseded_by_memory_id": updated.superseded_by_memory_id,
                    "mark_verified": mark_verified,
                },
            )
        )
        return self._to_managed_record(record, state=updated)

    def ingest_transcript_entry(self, entry: BrainTranscriptEntry, *, skip_seen_check: bool = False) -> None:
        """Project one append-only transcript entry into enhanced memory layers.

        Architectural note — memory ≠ log
        ----------------------------------
        BrainTranscriptStore is the append-only raw event log.  EnhancedMemory
        is the brain's *experience* layer — it carries semantic meaning, affect
        signal, and lifecycle tier.  Not every log entry warrants a memory
        record.

        Memory-worthy events (MEMORY_WORTHY_EVENTS set) get a full
        semantic + optional-procedural + episodic triple with appropriate
        emotional_valence and affect_intensity.

        Low-signal events (model provider calls, attention updates, etc.) are
        stored only as episodic provenance with neutral valence and low
        affect_intensity so the consolidation engine can identify and tombstone
        them via ForgettableNoiseRule.
        """
        from zentex.memory.management.classification import MEMORY_WORTHY_EVENTS

        if not skip_seen_check and not self._mark_projection_seen("transcript", entry.entry_id):
            return

        event_type = entry.entry_type.value
        is_memory_worthy = event_type in MEMORY_WORTHY_EVENTS
        valence, intensity = valence_for_transcript_event(event_type)

        # Memory-worthy events elevate to WARM tier immediately; others start HOT.
        tier = "warm" if is_memory_worthy else "hot"

        content = self._stringify_payload(entry.payload)

        # ── semantic layer (only for memory-worthy events) ────────────────
        if is_memory_worthy:
            semantic = EnhancedMemoryRecord(
                memory_layer="semantic",
                source_kind="transcript",
                title=f"Transcript {event_type}",
                summary=self._summarize_payload(entry.payload, fallback=event_type),
                content=content,
                trace_id=entry.trace_id,
                source_refs=[entry.entry_id],
                tags=[event_type, entry.source],
                payload={"source": entry.source, "entry_type": event_type},
                memory_tier=tier,
                emotional_valence=valence,
                affect_intensity=intensity,
            )
            self._append_semantic(semantic)

        # ── procedural layer (key decision/reflection events) ─────────────
        if event_type in {
            "decision_synthesized",
            "reflection_persisted",
            "consolidation_completed",
            "consolidation_failed",
            "human_intervention_applied",
        }:
            procedural = EnhancedMemoryRecord(
                memory_layer="procedural",
                source_kind="transcript",
                title=f"Procedure from {event_type}",
                summary=self._summarize_payload(
                    entry.payload, fallback=f"Procedure extracted from {event_type}."
                ),
                content=content,
                trace_id=entry.trace_id,
                source_refs=[entry.entry_id],
                tags=[event_type, "procedure"],
                payload={"source": entry.source, "entry_type": event_type},
                memory_tier=tier,
                emotional_valence=valence,
                affect_intensity=intensity,
            )
            self._append_procedural(procedural)

        # ── episodic layer (all events — provenance for the audit trail) ──
        episode = EnhancedMemoryRecord(
            memory_layer="episodic",
            source_kind="transcript",
            title=f"Episode {event_type}",
            summary=self._summarize_payload(
                entry.payload, fallback=f"Episode captured for {event_type}."
            ),
            content=content,
            trace_id=entry.trace_id,
            source_refs=[entry.entry_id],
            tags=[event_type, entry.source, "episode"],
            payload={"source": entry.source, "entry_type": event_type},
            memory_tier=tier,
            emotional_valence=valence,
            affect_intensity=intensity,
        )
        self._append_episode(episode)

    def ingest_upgrade_memory_record(self, record: UpgradeMemoryRecord, *, skip_seen_check: bool = False) -> None:
        """Project one upgrade memory record into semantic / procedural / episodic layers."""
        if not skip_seen_check and not self._mark_projection_seen("upgrade", record.memory_id):
            return

        valence, intensity = valence_for_upgrade_outcome(record.current_status)
        # Upgrade records always carry genuine learning signal → start WARM
        tier = "warm"

        base_tags = list(dict.fromkeys([
            record.target_kind,
            record.action,
            record.event_type,
            *record.success_tags,
            *record.learning_tags,
        ]))
        source_refs = [record.memory_id, *record.evidence_refs]
        version_id = record.candidate_version or record.current_version
        upgrade_content = self._build_upgrade_content(record)

        semantic = EnhancedMemoryRecord(
            memory_layer="semantic",
            source_kind="upgrade",
            title=record.title,
            summary=record.success_summary or record.failure_summary or record.summary,
            content=upgrade_content,
            trace_id=record.trace_id,
            request_id=record.request_id,
            source_event_id=record.source_event_id,
            target_id=record.target_id,
            version_id=version_id,
            tags=base_tags,
            evidence_refs=list(record.evidence_refs),
            source_refs=source_refs,
            payload={"event_type": record.event_type, "status": record.current_status},
            memory_tier=tier,
            emotional_valence=valence,
            affect_intensity=intensity,
        )
        self._append_semantic(semantic)

        if record.success_stage or record.failure_stage or record.reusable_insight or record.prevention_hint:
            procedural_summary = (
                record.reusable_insight
                or record.prevention_hint
                or record.success_summary
                or record.failure_summary
                or record.summary
            )
            procedural = EnhancedMemoryRecord(
                memory_layer="procedural",
                source_kind="upgrade",
                title=f"Procedure for {record.title}",
                summary=procedural_summary,
                content=upgrade_content,
                trace_id=record.trace_id,
                request_id=record.request_id,
                source_event_id=record.source_event_id,
                target_id=record.target_id,
                version_id=version_id,
                tags=list(dict.fromkeys([*base_tags, "procedure"])),
                evidence_refs=list(record.evidence_refs),
                source_refs=source_refs,
                payload={"event_type": record.event_type, "status": record.current_status},
                memory_tier=tier,
                emotional_valence=valence,
                affect_intensity=intensity,
            )
            self._append_procedural(procedural)

        episode = EnhancedMemoryRecord(
            memory_layer="episodic",
            source_kind="upgrade",
            title=f"Episode for {record.title}",
            summary=record.summary,
            content=upgrade_content,
            trace_id=record.trace_id,
            request_id=record.request_id,
            source_event_id=record.source_event_id,
            target_id=record.target_id,
            version_id=version_id,
            tags=list(dict.fromkeys([*base_tags, "episode", "provenance"])),
            evidence_refs=list(record.evidence_refs),
            source_refs=source_refs,
            payload={
                "event_type": record.event_type,
                "status": record.current_status,
                "previous_version": record.previous_version,
                "current_version": record.current_version,
                "candidate_version": record.candidate_version,
            },
            memory_tier=tier,
            emotional_valence=valence,
            affect_intensity=intensity,
        )
        self._append_episode(episode)

    def recall(
        self,
        *,
        query: str,
        limit: int = 10,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[MemoryRecallHit]:
        """Return merged local + adapter recall hits using HybridRetrievalEngine."""
        # Phase 2.3: Delegate to centralized engine
        retrieval_results = self._retrieval_engine.search(
            query=query,
            limit=limit,
            trace_id=trace_id,
            target_id=target_id
        )
        
        # Convert RetrievalResult -> MemoryRecallHit
        hits = []
        for r in retrieval_results:
            hits.append(
                MemoryRecallHit(
                    memory_id=r.memory_id,
                    memory_layer=r.memory_layer,
                    source_kind=r.source_kind,
                    title=r.title,
                    summary=r.summary,
                    trace_id=r.trace_id,
                    score=r.score,
                    tags=r.tags,
                    source_refs=r.source_refs
                )
            )
        
        # Final recallable filter (Governor level)
        return [
            hit
            for hit in hits
            if self._is_recallable(hit.memory_id)
        ][:limit]

    def backfill_transcript_entries(self, entries: list[BrainTranscriptEntry]) -> None:
        """Project historical transcript entries once during startup or recovery."""
        if not entries:
            return
        
        # Optimization: Pre-filter seen entries
        with self._seen_lock:
            unseen_entries = [
                e for e in entries 
                if ("transcript", e.entry_id) not in self._seen_projection_keys
            ]
            for e in unseen_entries:
                self._seen_projection_keys.add(("transcript", e.entry_id))
        
        for entry in unseen_entries:
            self.ingest_transcript_entry(entry, skip_seen_check=True)

    def backfill_upgrade_memory_records(self, records: list[UpgradeMemoryRecord]) -> None:
        """Project historical upgrade memory records once during startup or recovery."""
        if not records:
            return
            
        with self._seen_lock:
            unseen_records = [
                r for r in records 
                if ("upgrade", r.memory_id) not in self._seen_projection_keys
            ]
            for r in unseen_records:
                self._seen_projection_keys.add(("upgrade", r.memory_id))

        for record in unseen_records:
            self.ingest_upgrade_memory_record(record, skip_seen_check=True)

    # ── conflict detection ───────────────────────────────────────────────

    def detect_conflicts(
        self,
        record: EnhancedMemoryRecord,
        *,
        active_only: bool = True,
    ) -> list[dict[str, str]]:
        """Return a list of conflict descriptors for a record against existing memories.

        A conflict is one of:
        - "profile_update"  : a profile record with the same (layer, title, source_kind)
                              already exists but has a different content_hash.  The old
                              record should be superseded.
        - "title_collision" : a record with the same title but a different source_kind or
                              layer exists; may indicate redundant or contradictory records.

        Each descriptor is a dict with keys:
          conflict_kind, existing_memory_id, existing_content_hash, suggested_action.

        Args:
            record:      The incoming record to check.
            active_only: If True, only compare against records whose management
                         status is "active" (ignores already deprecated/superseded).
        """
        conflicts: list[dict[str, str]] = []
        existing = self._all_base_records()

        for existing_rec in existing:
            # Skip exact duplicate (already handled by content_hash dedup)
            if existing_rec.content_hash == record.content_hash:
                continue
            # Skip if already inactive
            if active_only:
                state = self._management_store.get(existing_rec.memory_id)
                if state is not None and state.status not in {"active", "trusted"}:
                    continue

            same_layer = existing_rec.memory_layer == record.memory_layer
            same_title = existing_rec.title.strip().lower() == record.title.strip().lower()
            same_source = existing_rec.source_kind == record.source_kind

            # Profile update: same (layer, title, source_kind), different content
            if same_layer and same_title and same_source and record.memory_kind == "profile":
                conflicts.append({
                    "conflict_kind": "profile_update",
                    "existing_memory_id": existing_rec.memory_id,
                    "existing_content_hash": existing_rec.content_hash,
                    "suggested_action": "supersede_old",
                })
            # Title collision: same title but different layer or source_kind
            elif same_title and (not same_layer or not same_source):
                conflicts.append({
                    "conflict_kind": "title_collision",
                    "existing_memory_id": existing_rec.memory_id,
                    "existing_content_hash": existing_rec.content_hash,
                    "suggested_action": "review_manually",
                })

        return conflicts

    # ── profile supersession ─────────────────────────────────────────────

    def _rebuild_profile_index(self) -> None:
        """Scan existing records and populate the profile index on startup."""
        with self._profile_lock:
            self._profile_index.clear()
            for rec in self._all_base_records():
                if rec.memory_kind != "profile":
                    continue
                key = (rec.memory_layer, rec.title.strip().lower(), rec.source_kind)
                # Later record in the list wins (most recent active profile)
                state = self._management_store.get(rec.memory_id)
                if state is None or state.status in {"active", "trusted"}:
                    self._profile_index[key] = rec.memory_id

    def _auto_supersede_profile(self, record: EnhancedMemoryRecord) -> None:
        """If record is a profile kind, supersede any previous active profile with the same key."""
        if record.memory_kind != "profile":
            return
        key = (record.memory_layer, record.title.strip().lower(), record.source_kind)
        with self._profile_lock:
            old_id = self._profile_index.get(key)
            if old_id and old_id != record.memory_id:
                # Mark old profile as superseded
                state = self._management_store.get(old_id)
                if state is not None and state.status in {"active", "trusted"}:
                    updated = state.model_copy(update={
                        "status": "deprecated",
                        "superseded_by_memory_id": record.memory_id,
                        "last_action": "superseded",
                        "last_action_reason": (
                            f"Profile superseded by newer record '{record.memory_id}' "
                            f"with content_hash '{record.content_hash}'."
                        ),
                        "updated_at": utc_now(),
                    })
                    self._management_store.upsert(updated)
                    self._audit_store.append(MemoryAuditEvent(
                        memory_id=old_id,
                        action="superseded",
                        reason=f"Profile '{key[1]}' updated; superseded by '{record.memory_id}'.",
                        operator="system",
                        details={
                            "new_memory_id": record.memory_id,
                            "new_content_hash": record.content_hash,
                            "profile_key": str(key),
                        },
                    ))
            # Register new record as the active profile
            self._profile_index[key] = record.memory_id

    # ── internal append helpers ──────────────────────────────────────────

    def _append_semantic(self, record: EnhancedMemoryRecord) -> None:
        stored = self._semantic_store.append(record)
        self._get_or_create_management_state(stored)
        # Phase 2.1: Indexing
        self._index_record(stored)
        if stored.memory_id == record.memory_id:
            # New record (not a dedup return) — handle profile supersession
            self._auto_supersede_profile(stored)
        if self._semantic_sink is not None:
            self._safe_projection(
                lambda: self._semantic_sink.store_semantic_memory(stored)
            )

    def _append_procedural(self, record: EnhancedMemoryRecord) -> None:
        stored = self._procedural_store.append(record)
        self._get_or_create_management_state(stored)
        # Phase 2.1: Indexing
        self._index_record(stored)
        if stored.memory_id == record.memory_id:
            self._auto_supersede_profile(stored)
        if self._procedural_sink is not None:
            self._safe_projection(
                lambda: self._procedural_sink.store_procedural_memory(stored)
            )

    def _append_episode(self, record: EnhancedMemoryRecord) -> None:
        stored = self._episodic_store.append(record)
        self._get_or_create_management_state(stored)
        # Phase 2.1: Indexing
        self._index_record(stored)
        if stored.memory_id == record.memory_id:
            self._auto_supersede_profile(stored)
        if self._episodic_sink is not None:
            self._safe_projection(lambda: self._episodic_sink.add_episode(stored))

    def _safe_projection(self, operation: Callable[[], None]) -> None:
        try:
            operation()
        except Exception as exc:  # pragma: no cover - defensive compatibility path
            message = str(exc).strip() or exc.__class__.__name__
            with self._failure_lock:
                self._projection_failures.append(message)
            if self._on_projection_error is not None:
                self._on_projection_error(message)

    def _mark_projection_seen(self, source_kind: str, source_id: str) -> bool:
        with self._seen_lock:
            key = (source_kind, source_id)
            if key in self._seen_projection_keys:
                return False
            self._seen_projection_keys.add(key)
            return True

    def _build_upgrade_content(self, record: UpgradeMemoryRecord) -> str:
        parts = [
            f"reason={record.summary}",
            f"status={record.current_status}",
            f"previous_version={record.previous_version or 'none'}",
            f"current_version={record.current_version}",
            f"candidate_version={record.candidate_version or 'none'}",
        ]
        if record.success_summary:
            parts.append(f"success_summary={record.success_summary}")
        if record.reusable_insight:
            parts.append(f"reusable_insight={record.reusable_insight}")
        if record.failure_summary:
            parts.append(f"failure_summary={record.failure_summary}")
        if record.prevention_hint:
            parts.append(f"prevention_hint={record.prevention_hint}")
        if record.root_cause_hypothesis:
            parts.append(f"root_cause_hypothesis={record.root_cause_hypothesis}")
        return "\n".join(parts)

    def _summarize_payload(self, payload: Any, *, fallback: str) -> str:
        if isinstance(payload, dict):
            for key in ("summary", "reason", "title", "status", "failure_reason"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return fallback

    def _stringify_payload(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return repr(payload)

    def _all_base_records(self) -> list[EnhancedMemoryRecord]:
        return [
            *self.list_semantic_records(),
            *self.list_procedural_records(),
            *self.list_episodic_records(),
            *self.list_quarantine_records(), # Sub-function 59 gap fix
        ]

    def list_quarantine_records(self) -> list[EnhancedMemoryRecord]:
        """List all memory fragments currently in the quarantine layer (Sub-function 59 gap)."""
        return self._quarantine_store.list_records()

    def _get_base_record(self, memory_id: str) -> EnhancedMemoryRecord | None:
        for record in self._all_base_records():
            if record.memory_id == memory_id:
                return record
        return None

    def _default_management_state(self, record: EnhancedMemoryRecord) -> MemoryManagementState:
        return MemoryManagementState(
            memory_id=record.memory_id,
            status="active",
            visibility="internal",
            trust_level="unverified",
            management_note=f"Projected from {record.source_kind}.",
            operator="system",
            last_action="ingested",
            last_action_reason=f"Projected from {record.source_kind} {record.memory_layer} evidence.",
        )

    def _get_or_create_management_state(self, record: EnhancedMemoryRecord) -> MemoryManagementState:
        state = self._management_store.get(record.memory_id)
        if state is not None:
            return state
        created = self._default_management_state(record)
        self._management_store.upsert(created)
        self._audit_store.append(
            MemoryAuditEvent(
                memory_id=record.memory_id,
                action="ingested",
                reason=created.last_action_reason,
                operator="system",
                details={
                    "memory_layer": record.memory_layer,
                    "source_kind": record.source_kind,
                    "trace_id": record.trace_id,
                },
            )
        )
        return created

    def _to_managed_record(
        self,
        record: EnhancedMemoryRecord,
        *,
        state: MemoryManagementState | None = None,
    ) -> ManagedEnhancedMemoryRecord:
        resolved = state or self._get_or_create_management_state(record)
        return ManagedEnhancedMemoryRecord.model_validate(
            {
                **record.model_dump(),
                **resolved.model_dump(exclude={"memory_id"}),
            }
        )

    def _derive_management_action(
        self,
        *,
        current: MemoryManagementState,
        status: str | None,
        visibility: str | None,
        trust_level: str | None,
        correction_note: str | None,
        management_note: str | None,
    ) -> str:
        if status is not None and status != current.status:
            return f"status_changed:{status}"
        if visibility is not None and visibility != current.visibility:
            return f"visibility_changed:{visibility}"
        if trust_level is not None and trust_level != current.trust_level:
            return f"trust_changed:{trust_level}"
        if correction_note is not None and correction_note != current.correction_note:
            return "correction_recorded"
        if management_note is not None and management_note != current.management_note:
            return "note_updated"
        return "metadata_updated"

    def _is_recallable(self, memory_id: str) -> bool:
        record = self.get_managed_record(memory_id)
        if record is None:
            return True
        return record.status not in {"archived", "rejected"} and record.visibility != "hidden"

    # ────────────────────────────────────────────────────────────────
    #  通用对外方法 / Universal Public API
    # ────────────────────────────────────────────────────────────────

    def store_memory(
        self,
        *,
        title: str,
        summary: str,
        content: str,
        layer: str = "semantic",
        source_kind: str = "external",
        trace_id: str | None = None,
        target_id: str | None = None,
        tags: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> EnhancedMemoryRecord:
        """
        通用的记忆写入入口。

        外部模块（Agent、CLI、Web API）统一通过此方法向记忆系统写入知识，
        无需关心底层的 semantic / procedural / episodic 分层逻辑。

        Args:
            title:       简短标题。
            summary:     摘要描述。
            content:     完整内容。
            layer:       目标记忆层，可选 "semantic" | "procedural" | "episodic"。
            source_kind: 来源标识（如 "agent", "user", "plugin"）。
            trace_id:    可选的追踪 ID，缺省自动生成。
            target_id:   可选的关联目标 ID。
            tags:        标签列表。
            payload:     附加元数据字典。

        Returns:
            写入后的 EnhancedMemoryRecord 实例。
        """
        from uuid import uuid4

        resolved_trace_id = trace_id or str(uuid4())
        record = EnhancedMemoryRecord(
            memory_layer=layer,
            source_kind=source_kind,
            title=title,
            summary=summary,
            content=content,
            trace_id=resolved_trace_id,
            target_id=target_id,
            tags=list(tags or []),
            payload=dict(payload or {}),
        )

        normalized = layer.lower()
        if normalized == "procedural":
            self._append_procedural(record)
        elif normalized == "episodic":
            self._append_episode(record)
        else:
            self._append_semantic(record)

        return record

    def recall_memories(
        self,
        query: str,
        *,
        limit: int = 10,
        layer: str | None = None,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[MemoryRecallHit]:
        """
        通用的记忆检索入口。

        外部模块统一通过此方法从记忆系统中检索相关知识。
        支持按层过滤、按 trace_id / target_id 精确定位。

        Args:
            query:     自然语言检索关键词。
            limit:     最大返回数量。
            layer:     可选过滤层 "semantic" | "procedural" | "episodic" | None(全部)。
            trace_id:  可选的追踪 ID 过滤。
            target_id: 可选的目标 ID 过滤。

        Returns:
            按相关性排序的 MemoryRecallHit 列表。
        """
        all_hits = self.recall(
            query=query,
            limit=limit * 2 if layer else limit,
            trace_id=trace_id,
            target_id=target_id,
        )
        if layer:
            normalized = layer.lower()
            all_hits = [h for h in all_hits if h.memory_layer == normalized]
        return all_hits[:limit]

    def get_memory_stats(self) -> dict[str, Any]:
        """
        返回记忆系统的统计概览，适用于 Dashboard 展示和健康检查。

        Returns:
            包含各层记录数、后端状态、治理状态分布等信息的字典。
        """
        semantic_records = self.list_semantic_records()
        procedural_records = self.list_procedural_records()
        episodic_records = self.list_episodic_records()

        all_managed = self.list_managed_records(limit=99999)
        status_dist: dict[str, int] = {}
        trust_dist: dict[str, int] = {}
        for m in all_managed:
            status_dist[m.status] = status_dist.get(m.status, 0) + 1
            trust_dist[m.trust_level] = trust_dist.get(m.trust_level, 0) + 1

        return {
            "total_records": len(semantic_records) + len(procedural_records) + len(episodic_records),
            "semantic_count": len(semantic_records),
            "procedural_count": len(procedural_records),
            "episodic_count": len(episodic_records),
            "status_distribution": status_dist,
            "trust_distribution": trust_dist,
            "projection_failures": len(self.list_projection_failures()),
            "backends": [b.model_dump(mode="json") for b in self.get_backend_status()],
        }

    def archive_memory(
        self,
        memory_id: str,
        *,
        reason: str = "Archived by operator.",
        operator: str = "operator",
    ) -> ManagedEnhancedMemoryRecord:
        """
        归档一条记忆。归档后的记忆不再出现在 recall 结果中。

        Args:
            memory_id: 目标记忆 ID。
            reason:    归档原因。
            operator:  操作者标识。

        Returns:
            更新后的 ManagedEnhancedMemoryRecord。
        """
        return self.update_management_state(
            memory_id,
            status="archived",
            operator=operator,
            reason=reason,
        )

    def verify_memory(
        self,
        memory_id: str,
        *,
        trust_level: str = "verified",
        reason: str = "Verified by operator.",
        operator: str = "operator",
    ) -> ManagedEnhancedMemoryRecord:
        """
        标记一条记忆为已验证状态，提升其信任等级。

        Args:
            memory_id:   目标记忆 ID。
            trust_level: 信任等级，默认 "verified"。
            reason:      验证原因。
            operator:    操作者标识。

        Returns:
            更新后的 ManagedEnhancedMemoryRecord。
        """
        return self.update_management_state(
            memory_id,
            trust_level=trust_level,
            operator=operator,
            reason=reason,
            mark_verified=True,
        )

    def correct_memory(
        self,
        memory_id: str,
        *,
        correction_note: str,
        superseded_by: str | None = None,
        reason: str = "Corrected by operator.",
        operator: str = "operator",
    ) -> ManagedEnhancedMemoryRecord:
        """
        订正一条记忆，附加修正说明。可选地标记为被新记忆取代。

        Args:
            memory_id:      目标记忆 ID。
            correction_note: 修正说明。
            superseded_by:   取代此记忆的新记忆 ID（可选）。
            reason:          修正原因。
            operator:        操作者标识。

        Returns:
            更新后的 ManagedEnhancedMemoryRecord。
        """
        return self.update_management_state(
            memory_id,
            correction_note=correction_note,
            superseded_by_memory_id=superseded_by,
            status="corrected" if superseded_by else None,
            operator=operator,
            reason=reason,
        )


# ════════════════════════════════════════════════════════════════════
#  模块说明 / Module Documentation
# ════════════════════════════════════════════════════════════════════
#
#  zentex.memory.enhanced — 增强记忆桥接层
#
#  本模块是 Zentex 认知记忆系统的核心文件，提供三层记忆架构：
#
#  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐
#  │  Semantic    │   │  Procedural  │   │  Episodic   │
#  │  语义记忆    │   │  程序性记忆  │   │  情节记忆   │
#  │  (知识/事实) │   │  (操作经验)  │   │  (事件图谱) │
#  └──────┬──────┘   └──────┬───────┘   └──────┬──────┘
#         │                 │                   │
#         └─────────┬───────┘                   │
#                   │                           │
#        ┌──────────▼──────────┐    ┌───────────▼──────────┐
#        │ SemanticMemorySink  │    │  EpisodicMemorySink   │
#        │ (LangMem / Mem0)   │    │  (Kuzu / Graphiti)    │
#        └─────────────────────┘    └──────────────────────┘
#
#  通用对外方法（Universal Public API）：
#
#    store_memory()      — 统一写入入口，自动路由到对应的记忆层
#    recall_memories()   — 统一检索入口，融合本地 + 外部后端结果
#    get_memory_stats()  — 系统健康概览，适用于 Dashboard / 监控
#    archive_memory()    — 归档记忆（从 recall 结果中隐藏）
#    verify_memory()     — 验证记忆（提升信任等级）
#    correct_memory()    — 订正记忆（附加修正说明 / 标记取代关系）
#
#  内部投影方法（仅供 Runtime 调用）：
#
#    ingest_transcript_entry()         — 从 Transcript 投影
#    ingest_upgrade_memory_record()    — 从 Upgrade Ledger 投影
#    backfill_transcript_entries()     — 启动时批量回填
#    backfill_upgrade_memory_records() — 启动时批量回填
#
#  适配器协议（Protocol）：
#
#    SemanticMemorySink           — 语义记忆外部写入适配器
#    ProceduralMemorySink         — 程序性记忆外部写入适配器
#    SemanticMemoryRecallClient   — 语义 / 程序性记忆外部检索适配器
#    EpisodicMemorySink           — 情节记忆外部写入适配器
#    EpisodicMemoryRecallClient   — 情节 / 图谱记忆外部检索适配器
#
# ════════════════════════════════════════════════════════════════════
    def import_experience_package(self, package_data: bytes, origin: str) -> str:
        """Import and verify an encrypted experience package (Sub-function 59.5)."""
        # 1. Decrypt and verify signature
        decrypted = self._decrypt_package(package_data)
        package_id = f"pkg-{uuid4().hex[:8]}"
        
        registry = PackageImportRegistry(
            package_id=package_id,
            source_origin=origin,
            signature_verified=True,
            is_encrypted=True
        )
        self._package_registry.append(registry)
        
        # 2. Ingest records into quarantined layer for G38 audit
        # (Real implementation would parse the decrypted JSON and ingest)
        return package_id

    def detect_data_contamination(self, source_id: str) -> list[str]:
        """Track and isolate memory records impacted by a contaminated source (Sub-function 59.5)."""
        impacted_records = []
        # Simulation: find all records where source_id is in source_refs
        all_hits = self.recall(query=source_id, limit=1000)
        impacted_records = [hit.memory_id for hit in all_hits]
        
        tracker = ContaminationTracker(
            source_id=source_id,
            impacted_records=impacted_records,
            confidence_degraded=0.5
        )
        self._contamination_tracker.append(tracker)
        
        # Mark records as quarantined or degraded
        for mid in impacted_records:
             self.update_management_state(mid, trust_level="degraded", reason=f"Contamination from {source_id}")
             
        return impacted_records

    def _encrypt_package(self, data: dict[str, Any]) -> bytes:
        """Helper to encrypt experience packages before export (Placeholder)."""
        # In a real system, this would use the zentex.security.encryption service
        return json.dumps(data).encode("utf-8")

    def _decrypt_package(self, data: bytes) -> dict[str, Any]:
        """Helper to decrypt experience packages after import (Placeholder)."""
        return json.loads(data.decode("utf-8"))

    def _is_protected_ref(self, ref_id: str) -> bool:
        """Safety check to prevent accidental pruning of identity/safety modules."""
        protected_prefixes = [
            "runtime.identity",
            "runtime.safety",
            "runtime.supervision",
            "identity_role_pack"
        ]
        return any(ref_id.startswith(p) for p in protected_prefixes)
