from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

UTC = timezone.utc
LEARNING_EVENT_TYPE = "learning_engine_event"
LEARNING_OVERALL_EVENT_TYPE = "learning_overall_record"


@dataclass
class LearningStoreEntry:
    entry_id: str
    session_id: str
    turn_id: str
    trace_id: str
    entry_type: str
    payload: dict[str, Any]
    timestamp: str
    source: str = "zentex.learning"


class LearningStore:
    """Learning module's own durable event store."""

    def __init__(self, db_path: str | Path, *, session_id: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_id = session_id
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS learning_events (
                    entry_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL DEFAULT '',
                    trace_id TEXT NOT NULL DEFAULT '',
                    entry_type TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'zentex.learning',
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_learning_session ON learning_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_learning_trace ON learning_events(trace_id);
                CREATE INDEX IF NOT EXISTS idx_learning_entry_type ON learning_events(entry_type);
                CREATE INDEX IF NOT EXISTS idx_learning_timestamp ON learning_events(timestamp);
                """
            )
            self._conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _normalize_entry_type(entry_type: Any, payload: dict[str, Any]) -> str:
        raw = getattr(entry_type, "value", entry_type)
        text = str(raw or "").strip()
        if text:
            return text
        return str(payload.get("entry_type") or LEARNING_EVENT_TYPE).strip() or LEARNING_EVENT_TYPE

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> LearningStoreEntry:
        return LearningStoreEntry(
            entry_id=str(row["entry_id"]),
            session_id=str(row["session_id"]),
            turn_id=str(row["turn_id"] or ""),
            trace_id=str(row["trace_id"] or ""),
            entry_type=str(row["entry_type"] or ""),
            source=str(row["source"] or "zentex.learning"),
            timestamp=str(row["timestamp"] or ""),
            payload=json.loads(row["payload"] or "{}"),
        )

    def write_entry(
        self,
        *,
        session_id: str,
        turn_id: str,
        entry_type: Any,
        payload: dict,
        source: str,
        trace_id: str,
        entry_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        normalized_payload = dict(payload or {})
        normalized_entry_type = self._normalize_entry_type(entry_type, normalized_payload)
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO learning_events
                (entry_id, session_id, turn_id, trace_id, entry_type, source, timestamp, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id or str(uuid.uuid4()),
                    session_id,
                    turn_id,
                    trace_id,
                    normalized_entry_type,
                    source,
                    timestamp.isoformat() if timestamp else self._now_iso(),
                    json.dumps(normalized_payload, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def query_by_session(self, session_id: str, limit: int = 100) -> list[LearningStoreEntry]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entry_id, session_id, turn_id, trace_id, entry_type, source, timestamp, payload
                FROM learning_events
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def query_history_entries(
        self,
        *,
        session_id: str,
        entry_type: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LearningStoreEntry]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entry_id, session_id, turn_id, trace_id, entry_type, source, timestamp, payload
                FROM learning_events
                WHERE session_id = ? AND entry_type = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (session_id, entry_type, limit, max(0, offset)),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def count_history_entries(
        self,
        *,
        session_id: str,
        entry_type: str,
    ) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_events
                WHERE session_id = ? AND entry_type = ?
                """,
                (session_id, entry_type),
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def delete_entries(self, entry_ids: list[str]) -> int:
        if not entry_ids:
            return 0
        with self._lock:
            cursor = self._conn.executemany(
                "DELETE FROM learning_events WHERE entry_id = ?",
                [(entry_id,) for entry_id in entry_ids],
            )
            self._conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
