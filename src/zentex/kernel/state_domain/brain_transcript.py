from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Condition
from typing import Iterable, Optional, Any, Dict, List, Union
from uuid import uuid4
from collections.abc import Callable

from zentex.common.locking import get_lock_for_resource
from zentex.kernel.state_domain.brain_transcript_models import (
    BrainTranscriptEntry,
    BrainTranscriptEntryType,
    JSONValue,
)


class BrainTranscriptStore:
    def __init__(
        self,
        file_path: Union[str, Path],
        *,
        entry_listeners: Iterable[Callable[[BrainTranscriptEntry], Optional[None]]] = None,
    ) -> None:
        self._file_path = Path(file_path)
        if self._file_path.suffix == ".jsonl":
            self._file_path = self._file_path.with_suffix(".sqlite3")
        self._write_lock = get_lock_for_resource(str(self._file_path))
        self._revision_condition = Condition()
        self._revision = 0
        self._entry_listeners = list(entry_listeners or [])
        self._listener_failures: list[str] = []
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._file_path), check_same_thread=False, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._write_lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS transcript_entries (
                        entry_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        trace_id TEXT NOT NULL,
                        entry_type TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        source TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON transcript_entries(session_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_turn ON transcript_entries(turn_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_trace ON transcript_entries(trace_id);")
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise
            finally:
                conn.close()

    def _row_to_entry(self, row: tuple) -> BrainTranscriptEntry:
        return BrainTranscriptEntry(
            entry_id=row[0],
            session_id=row[1],
            turn_id=row[2],
            trace_id=row[3],
            entry_type=BrainTranscriptEntryType(row[4]),
            timestamp=datetime.fromisoformat(row[5]),
            source=row[6],
            payload=json.loads(row[7]),
        )

    def append_entries(self, entries: Iterable[BrainTranscriptEntry]) -> list[BrainTranscriptEntry]:
        entries_list = list(entries)
        if not entries_list:
            return []
        with self._write_lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION;")
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO transcript_entries
                    (entry_id, session_id, turn_id, trace_id, entry_type, timestamp, source, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            e.entry_id,
                            e.session_id,
                            e.turn_id,
                            e.trace_id,
                            e.entry_type.value,
                            e.timestamp.isoformat(),
                            e.source,
                            json.dumps(e.payload, ensure_ascii=False) if e.payload is not None else "{}",
                        )
                        for e in entries_list
                    ],
                )
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise
            finally:
                conn.close()

        for entry in entries_list:
            for listener in list(self._entry_listeners):
                try:
                    listener(entry)
                except Exception as exc:  # pragma: no cover
                    self._listener_failures.append(str(exc).strip() or exc.__class__.__name__)
        with self._revision_condition:
            self._revision += 1
            self._revision_condition.notify_all()
        return entries_list

    def add_entry_listener(self, listener: Callable[[BrainTranscriptEntry], Optional[None]]) -> None:
        """Subscribe a projection listener without changing transcript ownership."""
        if listener in self._entry_listeners:
            return
        self._entry_listeners.append(listener)

    def append_entry(self, entry: BrainTranscriptEntry) -> BrainTranscriptEntry:
        self.append_entries([entry])
        return entry

    def write_entry(
        self,
        *,
        session_id: str,
        turn_id: str,
        entry_type: BrainTranscriptEntryType,
        payload: JSONValue,
        source: str,
        trace_id: str,
        entry_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> BrainTranscriptEntry:
        entry = BrainTranscriptEntry(
            entry_id=entry_id or str(uuid4()),
            session_id=session_id,
            turn_id=turn_id,
            entry_type=entry_type,
            timestamp=timestamp or datetime.now(timezone.utc),
            payload=payload,
            source=source,
            trace_id=trace_id,
        )
        return self.append_entry(entry)

    def read_entries(
        self,
        *,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ) -> list[BrainTranscriptEntry]:
        query = "SELECT * FROM transcript_entries WHERE 1=1"
        params: list[str] = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if turn_id:
            query += " AND turn_id = ?"
            params.append(turn_id)
        query += " ORDER BY timestamp ASC"
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [self._row_to_entry(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def read_entries_by_trace_prefix(
        self,
        trace_prefix: str,
    ) -> list[BrainTranscriptEntry]:
        """
        Phase F: Query entries by trace_id prefix (e.g. 'task-audit:{task_id}:').
        Allows efficient retrieval of task-specific audit trails.
        """
        query = "SELECT * FROM transcript_entries WHERE trace_id LIKE ? ORDER BY timestamp ASC"
        params = [f"{trace_prefix}%"]
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [self._row_to_entry(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def close(self) -> None:
        """Compatibility no-op: connections are opened per operation."""
        return None
