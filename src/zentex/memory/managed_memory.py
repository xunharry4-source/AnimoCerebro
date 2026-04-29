"""SQLite-backed managed long-term memory for G29."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ManagedMemoryRecord(BaseModel):
    """Governable long-term memory record with provenance."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(default_factory=lambda: f"mem-{uuid4().hex[:12]}")
    trace_id: str
    request_id: str
    source_event_id: str
    memory_type: str = Field(pattern="^(fact|event|case|lesson|constraint|procedure)$")
    topic: str
    role: str
    risk_level: str = Field(pattern="^(low|medium|high|critical)$")
    content: str
    status: str = Field(default="active")
    visibility: str = Field(default="visible")
    trust_level: str = Field(default="verified")
    correction_note: str = ""
    supersedes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryQueryResult(BaseModel):
    """Ranked memory query result with an explanation."""

    model_config = ConfigDict(extra="forbid")

    record: ManagedMemoryRecord
    score: float
    explanation: str


class MemoryAuditEvent(BaseModel):
    """Audit event for a managed memory mutation."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=lambda: f"mem-audit-{uuid4().hex[:12]}")
    memory_id: str
    action: str
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SQLiteManagedMemoryStore:
    """SQLite compatibility store plus governance/audit layer."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        """Close the owned SQLite connection once."""
        conn = getattr(self, "_conn", None)
        if conn is None:
            return
        try:
            conn.close()
        finally:
            self._conn = None

    def remember(self, record: ManagedMemoryRecord) -> ManagedMemoryRecord:
        """Persist a memory and write an audit event."""

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.memory_id,
                    record.trace_id,
                    record.request_id,
                    record.source_event_id,
                    record.memory_type,
                    record.topic,
                    record.role,
                    record.risk_level,
                    record.content,
                    record.status,
                    record.visibility,
                    record.trust_level,
                    record.correction_note,
                    record.supersedes,
                    record.created_at.isoformat(),
                ),
            )
        self._audit(record.memory_id, "remember", "initial memory ingestion")
        return record

    def get(self, memory_id: str) -> ManagedMemoryRecord | None:
        """Return a memory by id."""

        row = self._conn.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def query(
        self,
        *,
        query_text: str,
        topic: str | None = None,
        role: str | None = None,
        risk_level: str | None = None,
        include_hidden: bool = False,
        limit: int = 10,
    ) -> list[MemoryQueryResult]:
        """Query active memories with structured filters and explainable ranking."""

        clauses = ["status = 'active'"]
        params: list[Any] = []
        if not include_hidden:
            clauses.append("visibility = 'visible'")
        if topic:
            clauses.append("topic = ?")
            params.append(topic)
        if role:
            clauses.append("role = ?")
            params.append(role)
        if risk_level:
            clauses.append("risk_level = ?")
            params.append(risk_level)
        where = " AND ".join(clauses)
        rows = self._conn.execute(f"SELECT * FROM memories WHERE {where}", params).fetchall()
        terms = [term.lower() for term in query_text.split() if term.strip()]
        results: list[MemoryQueryResult] = []
        for row in rows:
            record = self._row_to_record(row)
            searchable = f"{record.topic} {record.role} {record.risk_level} {record.content}".lower()
            hits = sum(1 for term in terms if term in searchable)
            structured_bonus = (1 if topic and record.topic == topic else 0) + (1 if risk_level and record.risk_level == risk_level else 0)
            risk_bonus = {"critical": 0.4, "high": 0.3, "medium": 0.2, "low": 0.1}[record.risk_level]
            score = float(hits + structured_bonus) + risk_bonus
            if score <= 0:
                continue
            results.append(
                MemoryQueryResult(
                    record=record,
                    score=score,
                    explanation=f"matched_terms={hits}; structured_bonus={structured_bonus}; risk_bonus={risk_bonus}",
                )
            )
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def update_governance(
        self,
        memory_id: str,
        *,
        status: str | None = None,
        visibility: str | None = None,
        trust_level: str | None = None,
        correction_note: str | None = None,
        reason: str,
    ) -> ManagedMemoryRecord:
        """Update governance fields and write an audit event."""

        current = self.get(memory_id)
        if current is None:
            raise KeyError(f"Unknown memory_id: {memory_id}")
        updated = current.model_copy(
            update={
                "status": status or current.status,
                "visibility": visibility or current.visibility,
                "trust_level": trust_level or current.trust_level,
                "correction_note": correction_note if correction_note is not None else current.correction_note,
            }
        )
        with self._conn:
            self._conn.execute(
                """
                UPDATE memories
                SET status = ?, visibility = ?, trust_level = ?, correction_note = ?
                WHERE memory_id = ?
                """,
                (updated.status, updated.visibility, updated.trust_level, updated.correction_note, memory_id),
            )
        self._audit(memory_id, "governance_update", reason)
        return updated

    def list_audit_events(self, memory_id: str) -> list[MemoryAuditEvent]:
        """Return audit events for one memory."""

        rows = self._conn.execute(
            "SELECT * FROM memory_audit_events WHERE memory_id = ? ORDER BY created_at ASC",
            (memory_id,),
        ).fetchall()
        return [
            MemoryAuditEvent(
                audit_id=row["audit_id"],
                memory_id=row["memory_id"],
                action=row["action"],
                reason=row["reason"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    role TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    correction_note TEXT NOT NULL,
                    supersedes TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_audit_events (
                    audit_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_filters ON memories(topic, role, risk_level, status, visibility)")

    def _audit(self, memory_id: str, action: str, reason: str) -> None:
        event = MemoryAuditEvent(memory_id=memory_id, action=action, reason=reason)
        with self._conn:
            self._conn.execute(
                "INSERT INTO memory_audit_events VALUES (?, ?, ?, ?, ?)",
                (event.audit_id, event.memory_id, event.action, event.reason, event.created_at.isoformat()),
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ManagedMemoryRecord:
        return ManagedMemoryRecord(
            memory_id=row["memory_id"],
            trace_id=row["trace_id"],
            request_id=row["request_id"],
            source_event_id=row["source_event_id"],
            memory_type=row["memory_type"],
            topic=row["topic"],
            role=row["role"],
            risk_level=row["risk_level"],
            content=row["content"],
            status=row["status"],
            visibility=row["visibility"],
            trust_level=row["trust_level"],
            correction_note=row["correction_note"],
            supersedes=row["supersedes"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
