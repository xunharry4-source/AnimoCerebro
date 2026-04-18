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
import sqlite3
from threading import RLock
from typing import Callable, Any

from zentex.upgrade.base_models import UpgradeTargetKind


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
    CANCELLED = "cancelled"


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
}
CANCELLED_STATUSES = {
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
    
    # Sub-function 60 gap: audit and description fields
    feature_change_details: str = ""
    functional_description: str = ""
    baseline_version_ref: str = ""
    failure_category: str = "" # logic_error, security_violation, validation_failed, runtime_exception
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
    payload: dict[str, Any] = field(default_factory=dict)  # For monitoring metrics and custom data

    def lifecycle_view(self) -> UpgradeLifecycleView:
        if self.current_status in WAITING_STATUSES:
            return UpgradeLifecycleView.WAITING
        if self.current_status in CANCELLED_STATUSES:
            return UpgradeLifecycleView.CANCELLED
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
            if self._file_path.suffix in {".json", ".jsonl"}:
                self._file_path = self._file_path.with_suffix(".sqlite3")
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
            if self._file_path is not None:
                return self._list_records_from_sqlite(
                    target_kind=target_kind,
                    lifecycle=lifecycle,
                    action=action,
                )
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
        with self._lock:
            if self._file_path is not None:
                return self._build_counts_from_sqlite(target_kind=target_kind)
        all_records = self.list_records(target_kind=target_kind, lifecycle=UpgradeLifecycleView.ALL)
        return {
            "all": len(all_records),
            "waiting": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.WAITING),
            "ongoing": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.ONGOING),
            "completed": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.COMPLETED),
            "failed": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.FAILED),
            "cancelled": sum(1 for item in all_records if item.lifecycle_view() is UpgradeLifecycleView.CANCELLED),
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

    def _list_records_from_sqlite(
        self,
        *,
        target_kind: UpgradeTargetKind | None = None,
        lifecycle: UpgradeLifecycleView = UpgradeLifecycleView.ALL,
        action: str | None = None,
    ) -> list[UpgradeManagementRecord]:
        if self._file_path is None or not self._file_path.exists():
            return []
        self._init_db_unlocked()
        where_clauses: list[str] = []
        params: list[str] = []
        if target_kind is not None:
            where_clauses.append("target_kind = ?")
            params.append(target_kind.value)
        if lifecycle is not UpgradeLifecycleView.ALL:
            where_clauses.append("lifecycle_view = ?")
            params.append(lifecycle.value)
        if action is not None:
            where_clauses.append("action = ?")
            params.append(action)
        sql = "SELECT payload FROM management_records"
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY updated_at DESC"
        records: list[UpgradeManagementRecord] = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, tuple(params))
            for row in cursor:
                try:
                    item = json.loads(str(row[0]))
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                records.append(self._record_from_payload(item))
        return records

    def _build_counts_from_sqlite(
        self,
        *,
        target_kind: UpgradeTargetKind | None = None,
    ) -> dict[str, int]:
        if self._file_path is None or not self._file_path.exists():
            return {
                "all": 0,
                "waiting": 0,
                "ongoing": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
            }
        self._init_db_unlocked()
        where_sql = ""
        params: tuple[str, ...] = ()
        if target_kind is not None:
            where_sql = "WHERE target_kind = ?"
            params = (target_kind.value,)
        counts = {
            "all": 0,
            "waiting": 0,
            "ongoing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        with self._get_connection() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM management_records {where_sql}",
                params,
            ).fetchone()
            counts["all"] = int(row[0]) if row is not None else 0
            cursor = conn.execute(
                f"""
                SELECT lifecycle_view, COUNT(*)
                FROM management_records
                {where_sql}
                GROUP BY lifecycle_view
                """,
                params,
            )
            lifecycle_map = {
                UpgradeLifecycleView.WAITING.value: "waiting",
                UpgradeLifecycleView.ONGOING.value: "ongoing",
                UpgradeLifecycleView.COMPLETED.value: "completed",
                UpgradeLifecycleView.FAILED.value: "failed",
                UpgradeLifecycleView.CANCELLED.value: "cancelled",
            }
            for lifecycle_value, count in cursor:
                key = lifecycle_map.get(str(lifecycle_value))
                if key is not None:
                    counts[key] = int(count)
        return counts

    def _load_records(self) -> dict[str, UpgradeManagementRecord]:
        if self._file_path is None or not self._file_path.exists():
            return {}
        self._init_db_unlocked()
        records: dict[str, UpgradeManagementRecord] = {}
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT payload FROM management_records ORDER BY created_at ASC")
            for row in cursor:
                try:
                    item = json.loads(str(row[0]))
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                record = self._record_from_payload(item)
                records[record.record_id] = record
        return records

    def _persist_unlocked(self) -> None:
        if self._file_path is None:
            return
        self._init_db_unlocked()
        ordered_records = sorted(self._records.values(), key=lambda item: item.created_at)
        with self._get_connection() as conn:
            conn.execute("DELETE FROM management_records")
            conn.executemany(
                """
                INSERT INTO management_records (
                    record_id,
                    target_kind,
                    action,
                    target_id,
                    title,
                    reason,
                    trace_id,
                    request_id,
                    current_status,
                    lifecycle_view,
                    current_progress,
                    created_at,
                    updated_at,
                    payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(record.record_id),
                        str(record.target_kind.value),
                        str(record.action),
                        str(record.target_id),
                        str(record.title),
                        str(record.reason),
                        str(record.trace_id),
                        str(record.request_id),
                        str(record.current_status.value),
                        str(record.lifecycle_view().value),
                        int(record.current_progress),
                        str(record.created_at.isoformat()),
                        str(record.updated_at.isoformat()),
                        json.dumps(self._record_to_payload(record), ensure_ascii=False),
                    )
                    for record in ordered_records
                ],
            )

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

    def _get_connection(self) -> sqlite3.Connection:
        if self._file_path is None:
            raise RuntimeError("UpgradeManagementStore file_path is not configured for SQLite persistence.")
        conn = sqlite3.connect(
            str(self._file_path),
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db_unlocked(self) -> None:
        if self._file_path is None:
            return
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS management_records (
                    record_id TEXT PRIMARY KEY,
                    target_kind TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    current_status TEXT NOT NULL,
                    lifecycle_view TEXT NOT NULL,
                    current_progress INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(management_records)")
            }
            required_columns: dict[str, str] = {
                "target_kind": "TEXT NOT NULL DEFAULT ''",
                "action": "TEXT NOT NULL DEFAULT ''",
                "target_id": "TEXT NOT NULL DEFAULT ''",
                "title": "TEXT NOT NULL DEFAULT ''",
                "reason": "TEXT NOT NULL DEFAULT ''",
                "trace_id": "TEXT NOT NULL DEFAULT ''",
                "request_id": "TEXT NOT NULL DEFAULT ''",
                "current_status": "TEXT NOT NULL DEFAULT ''",
                "lifecycle_view": "TEXT NOT NULL DEFAULT ''",
                "current_progress": "INTEGER NOT NULL DEFAULT 0",
            }
            for column_name, column_sql in required_columns.items():
                if column_name not in existing_columns:
                    conn.execute(
                        f"ALTER TABLE management_records ADD COLUMN {column_name} {column_sql}"
                    )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_management_updated_at ON management_records(updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_management_target_kind ON management_records(target_kind)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_management_status ON management_records(current_status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_management_lifecycle_view ON management_records(lifecycle_view)"
            )
