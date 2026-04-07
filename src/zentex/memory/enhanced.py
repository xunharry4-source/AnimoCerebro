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
from datetime import UTC, datetime
import asyncio
import json
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from zentex.runtime.transcript import BrainTranscriptEntry
    from zentex.upgrade.ledger import UpgradeMemoryRecord


def utc_now() -> datetime:
    return datetime.now(UTC)


class EnhancedMemoryRecord(BaseModel):
    """Unified local record for semantic, procedural, or episodic memory."""

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
    """Small append-only local compatibility store for enhanced memory layers."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file_path = Path(file_path) if file_path is not None else None
        self._lock = Lock()
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[EnhancedMemoryRecord] = []
        if self._file_path is not None and self._file_path.exists():
            with self._file_path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    raw = raw.strip()
                    if not raw:
                        continue
                    self._records.append(EnhancedMemoryRecord.model_validate(json.loads(raw)))

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    def append(self, record: EnhancedMemoryRecord) -> EnhancedMemoryRecord:
        with self._lock:
            if self._file_path is not None:
                with self._file_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))
                    handle.write("\n")
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
    ) -> None:
        self._semantic_store = _EnhancedMemoryJSONLStore(semantic_store_path)
        self._procedural_store = _EnhancedMemoryJSONLStore(procedural_store_path)
        self._episodic_store = _EnhancedMemoryJSONLStore(episodic_store_path)
        self._management_store = _MemoryManagementStateStore(management_store_path)
        self._audit_store = _MemoryAuditStore(audit_store_path)
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
    ) -> list[ManagedEnhancedMemoryRecord]:
        normalized = layer.lower()
        if normalized == "semantic":
            records = self.list_semantic_records()
        elif normalized == "procedural":
            records = self.list_procedural_records()
        elif normalized == "episodic":
            records = self.list_episodic_records()
        else:
            records = self._all_base_records()
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
        """Project one append-only transcript entry into enhanced memory layers."""
        if not skip_seen_check and not self._mark_projection_seen("transcript", entry.entry_id):
            return
        semantic = EnhancedMemoryRecord(
            memory_layer="semantic",
            source_kind="transcript",
            title=f"Transcript {entry.entry_type.value}",
            summary=self._summarize_payload(entry.payload, fallback=entry.entry_type.value),
            content=self._stringify_payload(entry.payload),
            trace_id=entry.trace_id,
            source_refs=[entry.entry_id],
            tags=[entry.entry_type.value, entry.source],
            payload={"source": entry.source, "entry_type": entry.entry_type.value},
        )
        self._append_semantic(semantic)

        if entry.entry_type.value in {
            "decision_synthesized",
            "reflection_persisted",
            "consolidation_completed",
            "consolidation_failed",
            "human_intervention_applied",
        }:
            procedural = EnhancedMemoryRecord(
                memory_layer="procedural",
                source_kind="transcript",
                title=f"Procedure from {entry.entry_type.value}",
                summary=self._summarize_payload(entry.payload, fallback=f"Procedure extracted from {entry.entry_type.value}."),
                content=self._stringify_payload(entry.payload),
                trace_id=entry.trace_id,
                source_refs=[entry.entry_id],
                tags=[entry.entry_type.value, "procedure"],
                payload={"source": entry.source, "entry_type": entry.entry_type.value},
            )
            self._append_procedural(procedural)

        episode = EnhancedMemoryRecord(
            memory_layer="episodic",
            source_kind="transcript",
            title=f"Episode {entry.entry_type.value}",
            summary=self._summarize_payload(entry.payload, fallback=f"Episode captured for {entry.entry_type.value}."),
            content=self._stringify_payload(entry.payload),
            trace_id=entry.trace_id,
            source_refs=[entry.entry_id],
            tags=[entry.entry_type.value, entry.source, "episode"],
            payload={"source": entry.source, "entry_type": entry.entry_type.value},
        )
        self._append_episode(episode)

    def ingest_upgrade_memory_record(self, record: UpgradeMemoryRecord, *, skip_seen_check: bool = False) -> None:
        """Project one upgrade memory record into semantic / procedural / episodic layers."""
        if not skip_seen_check and not self._mark_projection_seen("upgrade", record.memory_id):
            return
        base_tags = list(dict.fromkeys([
            record.target_kind,
            record.action,
            record.event_type,
            *record.success_tags,
            *record.learning_tags,
        ]))
        source_refs = [record.memory_id, *record.evidence_refs]
        version_id = record.candidate_version or record.current_version

        semantic = EnhancedMemoryRecord(
            memory_layer="semantic",
            source_kind="upgrade",
            title=record.title,
            summary=record.success_summary or record.failure_summary or record.summary,
            content=self._build_upgrade_content(record),
            trace_id=record.trace_id,
            request_id=record.request_id,
            source_event_id=record.source_event_id,
            target_id=record.target_id,
            version_id=version_id,
            tags=base_tags,
            evidence_refs=list(record.evidence_refs),
            source_refs=source_refs,
            payload={"event_type": record.event_type, "status": record.current_status},
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
                content=self._build_upgrade_content(record),
                trace_id=record.trace_id,
                request_id=record.request_id,
                source_event_id=record.source_event_id,
                target_id=record.target_id,
                version_id=version_id,
                tags=list(dict.fromkeys([*base_tags, "procedure"])),
                evidence_refs=list(record.evidence_refs),
                source_refs=source_refs,
                payload={"event_type": record.event_type, "status": record.current_status},
            )
            self._append_procedural(procedural)

        episode = EnhancedMemoryRecord(
            memory_layer="episodic",
            source_kind="upgrade",
            title=f"Episode for {record.title}",
            summary=record.summary,
            content=self._build_upgrade_content(record),
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
        """Return merged local + adapter recall hits."""
        hits = [
            *self._semantic_store.search(
                query=query,
                limit=limit,
                trace_id=trace_id,
                target_id=target_id,
            ),
            *self._procedural_store.search(
                query=query,
                limit=limit,
                trace_id=trace_id,
                target_id=target_id,
            ),
            *self._episodic_store.search(
                query=query,
                limit=limit,
                trace_id=trace_id,
                target_id=target_id,
            ),
        ]
        if self._semantic_recall_client is not None:
            hits.extend(
                self._semantic_recall_client.search_memories(
                    query=query,
                    limit=limit,
                    trace_id=trace_id,
                    target_id=target_id,
                )
            )
        if self._episodic_recall_client is not None:
            hits.extend(
                self._episodic_recall_client.search_graph(
                    query=query,
                    limit=limit,
                    trace_id=trace_id,
                    target_id=target_id,
                )
            )

        deduped: dict[tuple[str, str, str], MemoryRecallHit] = {}
        for hit in sorted(hits, key=lambda item: item.score, reverse=True):
            key = (hit.memory_id, hit.memory_layer, hit.trace_id)
            deduped.setdefault(key, hit)
        return [
            hit
            for hit in deduped.values()
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

    def _append_semantic(self, record: EnhancedMemoryRecord) -> None:
        self._semantic_store.append(record)
        self._get_or_create_management_state(record)
        if self._semantic_sink is not None:
            self._safe_projection(
                lambda: self._semantic_sink.store_semantic_memory(record)
            )

    def _append_procedural(self, record: EnhancedMemoryRecord) -> None:
        self._procedural_store.append(record)
        self._get_or_create_management_state(record)
        if self._procedural_sink is not None:
            self._safe_projection(
                lambda: self._procedural_sink.store_procedural_memory(record)
            )

    def _append_episode(self, record: EnhancedMemoryRecord) -> None:
        self._episodic_store.append(record)
        self._get_or_create_management_state(record)
        if self._episodic_sink is not None:
            self._safe_projection(lambda: self._episodic_sink.add_episode(record))

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
        ]

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
