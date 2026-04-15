"""TranscriptStore — SQLite-backed, thread-safe transcript persistence."""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from zentex.kernel.state_domain.transcript_models import (
    TranscriptEntry,
    TranscriptEntryType,
    TurnAuditSummary,
)

UTC = timezone.utc

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transcript_entries (
    entry_id   TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_id    TEXT NOT NULL DEFAULT '',
    timestamp  TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}'
);
"""

_INDEX_SESSION_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_session_id ON transcript_entries (session_id);"
)
_INDEX_TURN_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_turn_id ON transcript_entries (turn_id);"
)
_INDEX_TYPE_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_entry_type ON transcript_entries (entry_type);"
)


def _row_to_entry(row: tuple) -> TranscriptEntry:
    """Convert a DB row tuple to a TranscriptEntry."""
    entry_id, entry_type, session_id, turn_id, timestamp, payload_json = row
    entry = TranscriptEntry(
        entry_type=TranscriptEntryType(entry_type),
        session_id=session_id,
        turn_id=turn_id,
        payload=json.loads(payload_json),
        entry_id=entry_id,
        timestamp=timestamp,
    )
    # __post_init__ would overwrite entry_id/timestamp if they were empty;
    # we set them before construction so they survive as-is.
    return entry


class TranscriptStore:
    """Appends and queries transcript entries backed by a per-session SQLite file.

    The store is safe to use from multiple threads; a threading.Lock serialises
    all write operations and each query opens the connection in the calling thread.
    """

    def __init__(
        self,
        session_id: str,
        db_dir: str = "app_data/transcripts",
    ) -> None:
        self._session_id = session_id
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, f"{session_id}.db")
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
                _CREATE_TABLE_SQL
                + _INDEX_SESSION_SQL
                + _INDEX_TURN_SQL
                + _INDEX_TYPE_SQL
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, entry: TranscriptEntry) -> None:
        """Thread-safe insert of a TranscriptEntry into the database."""
        sql = (
            "INSERT OR IGNORE INTO transcript_entries "
            "(entry_id, entry_type, session_id, turn_id, timestamp, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        payload_json = json.dumps(entry.payload)
        with self._lock:
            self._conn.execute(
                sql,
                (
                    entry.entry_id,
                    str(entry.entry_type),
                    entry.session_id,
                    entry.turn_id,
                    entry.timestamp,
                    payload_json,
                ),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query_by_session(
        self, session_id: str, limit: int = 100
    ) -> list[TranscriptEntry]:
        """Return up to *limit* entries for *session_id*, newest first."""
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, timestamp, payload "
            "FROM transcript_entries "
            "WHERE session_id = ? "
            "ORDER BY timestamp DESC "
            "LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, (session_id, limit)).fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    def query_by_turn(self, turn_id: str) -> list[TranscriptEntry]:
        """Return all entries for *turn_id*, ordered by timestamp ASC."""
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, timestamp, payload "
            "FROM transcript_entries "
            "WHERE turn_id = ? "
            "ORDER BY timestamp ASC"
        )
        with self._lock:
            rows = self._conn.execute(sql, (turn_id,)).fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    def query_by_type(
        self, entry_type: TranscriptEntryType, limit: int = 50
    ) -> list[TranscriptEntry]:
        """Return up to *limit* entries of *entry_type*, newest first."""
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, timestamp, payload "
            "FROM transcript_entries "
            "WHERE entry_type = ? "
            "ORDER BY timestamp DESC "
            "LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, (str(entry_type), limit)).fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    # ------------------------------------------------------------------
    # Web Console Compatibility (Legacy Shims)
    # ------------------------------------------------------------------

    def get_entries_snapshot(self) -> list[TranscriptEntry]:
        """Web console compatibility: returns latest 1000 entries for the session."""
        return self.query_by_session(self._session_id, limit=1000)

    def read_by_turn_id(self, turn_id: str) -> list[TranscriptEntry]:
        """Web console compatibility: alias for query_by_turn."""
        return self.query_by_turn(turn_id)

    def read_by_trace_id(self, trace_id: str) -> list[TranscriptEntry]:
        """Web console compatibility: scans payloads for the specified trace_id.
        
        Note: Expensive operation as trace_id is not a primary column in this schema version.
        """
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, timestamp, payload "
            "FROM transcript_entries "
            "WHERE payload LIKE ? "
            "ORDER BY timestamp ASC"
        )
        with self._lock:
            rows = self._conn.execute(sql, (f'%"{trace_id}"%',)).fetchall()
        
        all_entries = [_row_to_entry(tuple(r)) for r in rows]
        # Precise filtering to avoid false positives from LIKE
        return [
            e for e in all_entries 
            if isinstance(e.payload, dict) and (
                e.payload.get("trace_id") == trace_id or 
                (e.payload.get("caller_context") and e.payload["caller_context"].get("trace_id") == trace_id)
            )
        ]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def build_turn_summary(self, turn_id: str) -> TurnAuditSummary | None:
        """Derive a TurnAuditSummary from the entries recorded for *turn_id*.

        Returns None if no entries exist for that turn.
        """
        entries = self.query_by_turn(turn_id)
        if not entries:
            return None

        # Derive session_id from first entry
        session_id = entries[0].session_id

        phase_count = sum(
            1 for e in entries if e.entry_type == TranscriptEntryType.phase_result
        )
        error_count = sum(
            1 for e in entries if e.entry_type == TranscriptEntryType.error
        )

        started_at = ""
        ended_at = ""
        for e in entries:
            if e.entry_type == TranscriptEntryType.turn_start:
                started_at = e.timestamp
            if e.entry_type == TranscriptEntryType.turn_end:
                ended_at = e.timestamp

        # Compute duration in ms if both timestamps are available
        duration_ms = 0.0
        if started_at and ended_at:
            try:
                t_start = datetime.fromisoformat(started_at)
                t_end = datetime.fromisoformat(ended_at)
                duration_ms = (t_end - t_start).total_seconds() * 1000.0
            except ValueError:
                pass

        return TurnAuditSummary(
            turn_id=turn_id,
            session_id=session_id,
            phase_count=phase_count,
            error_count=error_count,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()
