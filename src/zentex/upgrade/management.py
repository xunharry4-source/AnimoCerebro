from __future__ import annotations

"""
Persistent management ledger for LLM and plugin evolution jobs.

This module stores the current lifecycle state for upgrade and plugin creation
jobs so the web console can recover waiting, ongoing, completed, and failed
work after a process restart. Cancel handlers remain in-memory because they are
runtime callbacks, but the records themselves are durable.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
import json
from pathlib import Path
from threading import RLock
from typing import Callable


class UpgradeTargetKind(str, Enum):
    """Top-level upgrade target categories."""

    LLM = "llm"
    PLUGIN = "plugin"


class UpgradeLifecycleStatus(str, Enum):
    """Runtime status for upgrade and plugin creation jobs."""

    QUEUED = "queued"
    PLANNING = "planning"
    COPYING_SOURCE = "copying_source"
    SCAFFOLDING_CANDIDATE = "scaffolding_candidate"
    RUNNING = "running"
    VALIDATING = "validating"
    REGISTERED = "registered"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CLEANED_UP = "cleaned_up"


class UpgradeLifecycleView(str, Enum):
    """User-facing filter buckets for management pages."""

    ALL = "all"
    WAITING = "waiting"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    FAILED = "failed"


WAITING_STATUSES = {
    UpgradeLifecycleStatus.QUEUED,
}
ONGOING_STATUSES = {
    UpgradeLifecycleStatus.PLANNING,
    UpgradeLifecycleStatus.COPYING_SOURCE,
    UpgradeLifecycleStatus.SCAFFOLDING_CANDIDATE,
    UpgradeLifecycleStatus.RUNNING,
    UpgradeLifecycleStatus.VALIDATING,
    UpgradeLifecycleStatus.REGISTERED,
    UpgradeLifecycleStatus.ACTIVE,
}
COMPLETED_STATUSES = {
    UpgradeLifecycleStatus.COMPLETED,
    UpgradeLifecycleStatus.CLEANED_UP,
}
FAILED_STATUSES = {
    UpgradeLifecycleStatus.FAILED,
    UpgradeLifecycleStatus.CANCELLED,
}


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, kw_only=True)
class UpgradeManagementRecord:
    """Internal record for an LLM or plugin evolution job."""

    record_id: str
    target_kind: UpgradeTargetKind
    action: str
    target_id: str
    title: str
    reason: str
    trace_id: str
    request_id: str
    source_event_id: str | None = None
    parent_record_id: str | None = None
    change_summary: str
    function_summary: str
    previous_version: str | None
    current_version: str
    candidate_version: str | None
    current_status: UpgradeLifecycleStatus
    current_progress: int = 0
    success_stage: str | None = None
    success_summary: str | None = None
    reusable_insight: str | None = None
    successful_command: str | None = None
    success_artifact_refs: list[str] = field(default_factory=list)
    promotion_hint: str | None = None
    success_tags: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    failure_stage: str | None = None
    failure_code: str | None = None
    failure_summary: str | None = None
    root_cause_hypothesis: str | None = None
    failed_command: str | None = None
    failed_artifact_refs: list[str] = field(default_factory=list)
    retryable: bool | None = None
    prevention_hint: str | None = None
    learning_tags: list[str] = field(default_factory=list)
    source_path: str | None = None
    candidate_path: str | None = None
    memory_recall_query: str | None = None
    recalled_memory_ids: list[str] = field(default_factory=list)
    recalled_success_patterns: list[str] = field(default_factory=list)
    recalled_failure_patterns: list[str] = field(default_factory=list)
    recalled_suspect_patterns: list[str] = field(default_factory=list)
    memory_recall_summary: str | None = None
    audit_status: str = "pending"
    memory_status: str = "pending"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    evidence_refs: list[str] = field(default_factory=list)

    def lifecycle_view(self) -> UpgradeLifecycleView:
        if self.current_status in WAITING_STATUSES:
            return UpgradeLifecycleView.WAITING
        if self.current_status in FAILED_STATUSES:
            return UpgradeLifecycleView.FAILED
        if self.current_status in COMPLETED_STATUSES:
            return UpgradeLifecycleView.COMPLETED
        return UpgradeLifecycleView.ONGOING


class UpgradeManagementStore:
    """Thread-safe persistent store for upgrade management records."""

    def __init__(
        self,
        records: list[UpgradeManagementRecord] | None = None,
        *,
        file_path: str | Path | None = None,
    ) -> None:
        self._lock = RLock()
        self._file_path = Path(file_path) if file_path is not None else None
        if self._file_path is not None:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, UpgradeManagementRecord] = self._load_records()
        self._cancel_handlers: dict[str, Callable[[], None]] = {}
        for record in records or []:
            self._records[record.record_id] = record
        self._persist_unlocked()

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    def upsert(self, record: UpgradeManagementRecord) -> UpgradeManagementRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._records[record.record_id] = record
            self._persist_unlocked()
            return record

    def get(self, record_id: str) -> UpgradeManagementRecord:
        with self._lock:
            return self._records[record_id]

    def register_cancel_handler(
        self,
        record_id: str,
        handler: Callable[[], None],
    ) -> None:
        with self._lock:
            self._cancel_handlers[record_id] = handler

    def list_records(
        self,
        *,
        target_kind: UpgradeTargetKind | None = None,
        lifecycle: UpgradeLifecycleView = UpgradeLifecycleView.ALL,
        action: str | None = None,
    ) -> list[UpgradeManagementRecord]:
        with self._lock:
            records = list(self._records.values())

        filtered: list[UpgradeManagementRecord] = []
        for record in records:
            if target_kind is not None and record.target_kind is not target_kind:
                continue
            if lifecycle is not UpgradeLifecycleView.ALL and record.lifecycle_view() is not lifecycle:
                continue
            if action is not None and record.action != action:
                continue
            filtered.append(record)
        return sorted(filtered, key=lambda item: item.updated_at, reverse=True)

    def build_counts(
        self,
        *,
        target_kind: UpgradeTargetKind | None = None,
    ) -> dict[str, int]:
        all_records = self.list_records(target_kind=target_kind, lifecycle=UpgradeLifecycleView.ALL)
        return {
            "all": len(all_records),
            "waiting": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.WAITING),
            "ongoing": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.ONGOING),
            "completed": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.COMPLETED),
            "failed": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.FAILED),
        }

    def cancel(
        self,
        record_id: str,
        *,
        reason: str,
    ) -> UpgradeManagementRecord:
        with self._lock:
            record = self._records[record_id]
            if record.current_status not in WAITING_STATUSES | ONGOING_STATUSES:
                raise ValueError("Only waiting or ongoing upgrade records can be cancelled")
            if record.current_status in ONGOING_STATUSES:
                handler = self._cancel_handlers.get(record_id)
                if handler is None:
                    raise ValueError(
                        "Ongoing upgrade records require a real cancel handler"
                    )
                handler()
                self._cancel_handlers.pop(record_id, None)
            record.current_status = UpgradeLifecycleStatus.CANCELLED
            record.failure_reason = reason
            record.audit_status = "cancelled"
            record.memory_status = "persisted"
            record.finished_at = utc_now()
            record.updated_at = utc_now()
            self._persist_unlocked()
            return record

    def cleanup_failed_candidate(
        self,
        record_id: str,
        *,
        reason: str,
    ) -> UpgradeManagementRecord:
        with self._lock:
            record = self._records[record_id]
            if record.target_kind is not UpgradeTargetKind.PLUGIN:
                raise ValueError("Only plugin evolution records support failed candidate cleanup")
            if record.current_status not in FAILED_STATUSES:
                raise ValueError("Only failed plugin evolution records can be cleaned up")
            record.current_status = UpgradeLifecycleStatus.CLEANED_UP
            record.failure_reason = reason
            record.audit_status = "cleanup_completed"
            record.memory_status = "persisted"
            record.finished_at = utc_now()
            record.updated_at = utc_now()
            self._persist_unlocked()
            return record

    def _load_records(self) -> dict[str, UpgradeManagementRecord]:
        if self._file_path is None or not self._file_path.exists():
            return {}
        with self._file_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, list):
            return {}
        records: dict[str, UpgradeManagementRecord] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            record = self._record_from_payload(item)
            records[record.record_id] = record
        return records

    def _persist_unlocked(self) -> None:
        if self._file_path is None:
            return
        payload = [
            self._record_to_payload(record)
            for record in sorted(self._records.values(), key=lambda item: item.created_at)
        ]
        temp_path = self._file_path.with_suffix(f"{self._file_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path.replace(self._file_path)

    def _record_to_payload(self, record: UpgradeManagementRecord) -> dict[str, object]:
        payload = asdict(record)
        payload["target_kind"] = record.target_kind.value
        payload["current_status"] = record.current_status.value
        for key in (
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
        ):
            value = payload.get(key)
            payload[key] = value.isoformat() if isinstance(value, datetime) else None
        return payload

    def _record_from_payload(self, payload: dict[str, object]) -> UpgradeManagementRecord:
        normalized = dict(payload)
        normalized["target_kind"] = UpgradeTargetKind(str(normalized["target_kind"]))
        normalized["current_status"] = UpgradeLifecycleStatus(str(normalized["current_status"]))
        for key in ("created_at", "updated_at"):
            value = normalized.get(key)
            normalized[key] = datetime.fromisoformat(value) if isinstance(value, str) else utc_now()
        for key in ("started_at", "finished_at"):
            value = normalized.get(key)
            normalized[key] = datetime.fromisoformat(value) if isinstance(value, str) else None
        return UpgradeManagementRecord(**normalized)
