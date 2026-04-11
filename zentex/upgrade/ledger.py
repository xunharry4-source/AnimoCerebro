from __future__ import annotations

"""
Persistent audit and memory ledgers for upgrade execution history.

This module provides append-only JSONL stores for upgrade audit events and
upgrade memory snapshots. The stores are used to keep real, queryable evidence
for why an upgrade started, what changed, how it progressed, and why it ended.
"""

from datetime import UTC, datetime
import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

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
    source_event_id: str | None = None
    parent_record_id: str | None = None
    target_kind: str = Field(min_length=1)
    action: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    current_progress: int = Field(ge=0, le=100)
    previous_version: str | None = None
    current_version: str = Field(min_length=1)
    candidate_version: str | None = None
    success_stage: str | None = None
    success_summary: str | None = None
    reusable_insight: str | None = None
    successful_command: str | None = None
    success_artifact_refs: list[str] = Field(default_factory=list)
    promotion_hint: str | None = None
    success_tags: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    failure_stage: str | None = None
    failure_code: str | None = None
    failure_summary: str | None = None
    root_cause_hypothesis: str | None = None
    failed_command: str | None = None
    failed_artifact_refs: list[str] = Field(default_factory=list)
    retryable: bool | None = None
    prevention_hint: str | None = None
    learning_tags: list[str] = Field(default_factory=list)
    source_path: str | None = None
    candidate_path: str | None = None
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
    source_event_id: str | None = None
    parent_record_id: str | None = None
    target_kind: str = Field(min_length=1)
    action: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    memory_kind: str = Field(default="upgrade_history", min_length=1)
    event_type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    current_progress: int = Field(ge=0, le=100)
    previous_version: str | None = None
    current_version: str = Field(min_length=1)
    candidate_version: str | None = None
    success_stage: str | None = None
    success_summary: str | None = None
    reusable_insight: str | None = None
    successful_command: str | None = None
    success_artifact_refs: list[str] = Field(default_factory=list)
    promotion_hint: str | None = None
    success_tags: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    failure_stage: str | None = None
    failure_code: str | None = None
    failure_summary: str | None = None
    root_cause_hypothesis: str | None = None
    failed_command: str | None = None
    failed_artifact_refs: list[str] = Field(default_factory=list)
    retryable: bool | None = None
    prevention_hint: str | None = None
    learning_tags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class _JSONLStore:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file_path = Path(file_path) if file_path is not None else None
        self._lock = Lock()
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    def _append_line(self, payload: dict[str, Any]) -> None:
        if self._file_path is None:
            return
        line = json.dumps(payload, ensure_ascii=False)
        with self._file_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")

    def _read_lines(self) -> list[dict[str, Any]]:
        if self._file_path is None or not self._file_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self._file_path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                rows.append(json.loads(raw))
        return rows


class UpgradeAuditStore(_JSONLStore):
    """Append-only store for upgrade audit events."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        super().__init__(file_path)
        self._events: list[UpgradeAuditEvent] = [
            UpgradeAuditEvent.model_validate(row) for row in self._read_lines()
        ]

    def append_event(self, event: UpgradeAuditEvent) -> UpgradeAuditEvent:
        with self._lock:
            self._append_line(event.model_dump(mode="json"))
            self._events.append(event)
        return event

    def list_events(self, *, record_id: str | None = None) -> list[UpgradeAuditEvent]:
        with self._lock:
            events = list(self._events)
        if record_id is not None:
            events = [item for item in events if item.record_id == record_id]
        return sorted(events, key=lambda item: item.created_at)


class UpgradeMemoryStore(_JSONLStore):
    """Append-only store for upgrade memory snapshots."""

    def __init__(self, file_path: str | Path | None = None) -> None:
        super().__init__(file_path)
        self._records: list[UpgradeMemoryRecord] = [
            UpgradeMemoryRecord.model_validate(row) for row in self._read_lines()
        ]

    def append_record(self, record: UpgradeMemoryRecord) -> UpgradeMemoryRecord:
        with self._lock:
            self._append_line(record.model_dump(mode="json"))
            self._records.append(record)
        return record

    def list_records(self, *, record_id: str | None = None) -> list[UpgradeMemoryRecord]:
        with self._lock:
            records = list(self._records)
        if record_id is not None:
            records = [item for item in records if item.record_id == record_id]
        return sorted(records, key=lambda item: item.created_at)
