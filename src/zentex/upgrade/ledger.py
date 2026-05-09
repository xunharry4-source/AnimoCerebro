from __future__ import annotations

"""
Persistent audit and memory ledgers for upgrade execution history.

This module provides append-only JSONL stores for upgrade audit events and
upgrade memory snapshots. The stores are used to keep real, queryable evidence
for why an upgrade started, what changed, how it progressed, and why it ended.
"""

from datetime import datetime, timezone
UTC = timezone.utc
from contextlib import contextmanager
import json
import logging
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class UpgradeAuditEvent(BaseModel):
    """Structured audit event for one upgrade lifecycle transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    record_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    target_kind: str = Field(min_length=1)
    action: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    current_progress: int = Field(ge=0, le=100)
    previous_version: Optional[str] = None
    current_version: str = Field(min_length=1)
    candidate_version: Optional[str] = None
    success_stage: Optional[str] = None
    success_summary: Optional[str] = None
    reusable_insight: Optional[str] = None
    successful_command: Optional[str] = None
    success_artifact_refs: list[str] = Field(default_factory=list)
    promotion_hint: Optional[str] = None
    success_tags: list[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    failure_stage: Optional[str] = None
    failure_code: Optional[str] = None
    failure_summary: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    failed_command: Optional[str] = None
    failed_artifact_refs: list[str] = Field(default_factory=list)
    retryable: Optional[bool] = None
    prevention_hint: Optional[str] = None
    learning_tags: list[str] = Field(default_factory=list)
    source_path: Optional[str] = None
    candidate_path: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class UpgradeMemoryRecord(BaseModel):
    """Durable memory snapshot for one upgrade lifecycle transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str = Field(default_factory=lambda: str(uuid4()))
    record_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    target_kind: str = Field(min_length=1)
    action: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    memory_kind: str = Field(default="upgrade_history", min_length=1)
    event_type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    current_progress: int = Field(ge=0, le=100)
    previous_version: Optional[str] = None
    current_version: str = Field(min_length=1)
    candidate_version: Optional[str] = None
    success_stage: Optional[str] = None
    success_summary: Optional[str] = None
    reusable_insight: Optional[str] = None
    successful_command: Optional[str] = None
    success_artifact_refs: list[str] = Field(default_factory=list)
    promotion_hint: Optional[str] = None
    success_tags: list[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    failure_stage: Optional[str] = None
    failure_code: Optional[str] = None
    failure_summary: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    failed_command: Optional[str] = None
    failed_artifact_refs: list[str] = Field(default_factory=list)
    retryable: Optional[bool] = None
    prevention_hint: Optional[str] = None
    learning_tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class _SQLiteStore:
    def __init__(self, file_path: Union[str, Optional[Path]] = None) -> None:
        self._file_path = Path(file_path) if file_path is not None else None
        self._lock = Lock()
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            if self._file_path.suffix == ".jsonl":
                self._file_path = self._file_path.with_suffix(".sqlite3")

        if self._file_path is not None:
            self._init_db()
        else:
            self._memory_db = sqlite3.connect(":memory:", check_same_thread=False)
            self._init_schema(self._memory_db)

    @contextmanager
    def _get_connection(self):
        if self._file_path is None:
            yield self._memory_db
            return
        conn = sqlite3.connect(
            str(self._file_path),
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                self._init_schema(conn)

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ledger_records (
                id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                payload TEXT NOT NULL
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_record_id ON ledger_records(record_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trace_id ON ledger_records(trace_id)')

    @property
    def file_path(self) -> Optional[Path]:
        return self._file_path

    def close(self) -> None:
        """Close the in-memory SQLite connection held by memory-backed stores."""
        if self._file_path is not None:
            return
        with self._lock:
            conn = getattr(self, "_memory_db", None)
            if conn is None:
                return
            try:
                conn.close()
            finally:
                self._memory_db = None

    def _insert_payload(self, pk: str, record_id: str, trace_id: str, created_at: datetime, payload: dict[str, Any]) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO ledger_records (id, record_id, trace_id, created_at, payload) VALUES (?, ?, ?, ?, ?)",
                    (pk, record_id, trace_id, created_at.isoformat(), json.dumps(payload, ensure_ascii=False))
                )

    def _select_payloads(self, record_id: Optional[str] = None) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM ledger_records"
        params = []
        if record_id is not None:
            sql += " WHERE record_id = ?"
            params.append(record_id)
        sql += " ORDER BY created_at ASC"
        
        results = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor:
                try:
                    results.append(json.loads(row[0]))
                except Exception:
                    # POLICY[no-silent-except]: log corrupted DB row and skip it.
                    logger.warning("Skipping corrupted ledger row — invalid JSON", exc_info=True)
        return results


class UpgradeAuditStore(_SQLiteStore):
    """Append-only store for upgrade audit events."""

    def __init__(self, file_path: Union[str, Optional[Path]] = None) -> None:
        super().__init__(file_path)

    def append_event(self, event: UpgradeAuditEvent) -> UpgradeAuditEvent:
        self._insert_payload(
            pk=event.event_id,
            record_id=event.record_id,
            trace_id=event.trace_id,
            created_at=event.created_at,
            payload=event.model_dump(mode="json")
        )
        return event

    def list_events(self, *, record_id: Optional[str] = None) -> list[UpgradeAuditEvent]:
        return [UpgradeAuditEvent.model_validate(row) for row in self._select_payloads(record_id)]


class UpgradeMemoryStore(_SQLiteStore):
    """Append-only store for upgrade memory snapshots."""

    def __init__(self, file_path: Union[str, Optional[Path]] = None) -> None:
        super().__init__(file_path)

    def append_record(self, record: UpgradeMemoryRecord) -> UpgradeMemoryRecord:
        self._insert_payload(
            pk=record.memory_id,
            record_id=record.record_id,
            trace_id=record.trace_id,
            created_at=record.created_at,
            payload=record.model_dump(mode="json")
        )
        return record

    def list_records(self, *, record_id: Optional[str] = None) -> list[UpgradeMemoryRecord]:
        return [UpgradeMemoryRecord.model_validate(row) for row in self._select_payloads(record_id)]
