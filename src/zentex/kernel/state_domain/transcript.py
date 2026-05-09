from __future__ import annotations
"""TranscriptStore — SQLite-backed, thread-safe transcript persistence."""


from typing import Any, Callable, Dict, Iterable, List, Optional, Union

import json
import logging
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

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
    trace_id   TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT 'kernel',
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


def _column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    """Return True if *column* already exists in *table*.

    Uses PRAGMA table_info so we never need to attempt ALTER TABLE and swallow
    OperationalError — that pattern violates POLICY[no-silent-except].
    """
    cur.execute(f"PRAGMA table_info({table})")  # noqa: S608 — table is a local constant
    return any(row["name"] == column for row in cur.fetchall())


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Create tables, indexes, and run idempotent column migrations on *conn*.

    Deliberately module-level (not a method) so it can be called before
    self._conn is assigned during __init__ (needed for malformed-DB recovery).

    # POLICY[no-silent-except]: migrations use PRAGMA table_info to check
    # column existence instead of catching OperationalError silently.
    """
    cur = conn.cursor()
    cur.executescript(
        _CREATE_TABLE_SQL
        + _INDEX_SESSION_SQL
        + _INDEX_TURN_SQL
        + _INDEX_TYPE_SQL
    )
    # Idempotent column migrations — checked via PRAGMA, no exception swallowing.
    if not _column_exists(cur, "transcript_entries", "trace_id"):
        cur.execute(
            "ALTER TABLE transcript_entries ADD COLUMN trace_id TEXT NOT NULL DEFAULT ''"
        )
    if not _column_exists(cur, "transcript_entries", "source"):
        cur.execute(
            "ALTER TABLE transcript_entries ADD COLUMN source TEXT NOT NULL DEFAULT 'kernel'"
        )
    conn.commit()


def _row_to_entry(row: tuple) -> TranscriptEntry:
    """Convert a DB row tuple to a TranscriptEntry."""
    entry_id, entry_type_raw, session_id, turn_id, trace_id, source, timestamp, payload_json = row
    
    # RECOVERY SHIM: Python 3.11 'str(Enum)' can return 'Enum.Member' instead of 'value'.
    # If we find the prefix, strip it to avoid 'is not a valid TranscriptEntryType' errors.
    type_str = entry_type_raw
    if isinstance(type_str, str) and type_str.startswith("TranscriptEntryType."):
        type_str = type_str.split(".", 1)[1]

    try:
        et = TranscriptEntryType(type_str)
    except ValueError:
        logger.warning(
            "[TRANSCRIPT] Unknown entry_type '%s' in session %s. Falling back to 'state_change'.",
            type_str, session_id
        )
        et = TranscriptEntryType.state_change

    entry = TranscriptEntry(
        entry_type=et,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source=source,
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
        db_dir: Optional[str] = None,
        *,
        entry_listeners: Iterable[Callable[[TranscriptEntry], Optional[None]]] = (),
    ) -> None:
        if db_dir is None:
            from zentex.common.storage_paths import get_storage_paths

            db_dir = str(get_storage_paths().transcript_dir)
        self._session_id = session_id
        self._lock = threading.Lock()
        self._entry_listeners = list(entry_listeners or [])
        self._listener_failures: list[str] = []
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, f"{session_id}.db")
        self._conn = self._open_or_recover(db_path)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _open_or_recover(self, db_path: str) -> sqlite3.Connection:
        """Open the SQLite connection.  If the file is malformed (disk corruption,
        incomplete write, etc.) the corrupt file is moved to <path>.bak and a
        fresh database is created so the server can start cleanly.

        # POLICY[no-silent-except]: a corrupted database is logged as ERROR with
        # full traceback.  Silently swallowing DatabaseError here would crash the
        # ASGI server on every subsequent startup, hiding the root cause entirely.
        """
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            _apply_schema(conn)
        except sqlite3.DatabaseError:
            logger.error(
                "TranscriptStore: '%s' is malformed — backing up to .bak and recreating. "
                "Session transcript data for '%s' is lost.",
                db_path, self._session_id,
                exc_info=True,
            )
            try:
                conn.close()
            except Exception:
                logger.warning(
                    "TranscriptStore: could not close corrupt connection for '%s'",
                    db_path, exc_info=True,
                )
            bak_path = db_path + ".bak"
            try:
                shutil.move(db_path, bak_path)
                logger.warning("TranscriptStore: corrupt DB moved to '%s'", bak_path)
            except OSError:
                # POLICY[no-silent-except]: log backup failure before deleting.
                logger.warning(
                    "TranscriptStore: could not back up corrupt DB to '%s' — deleting instead",
                    bak_path, exc_info=True,
                )
                os.remove(db_path)
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _apply_schema(conn)
        return conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Apply schema / migrations to the live connection (thread-safe)."""
        with self._lock:
            _apply_schema(self._conn)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(self, entry: TranscriptEntry) -> None:
        """Thread-safe insert of a TranscriptEntry into the database."""
        sql = (
            "INSERT OR IGNORE INTO transcript_entries "
            "(entry_id, entry_type, session_id, turn_id, trace_id, source, timestamp, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        payload_json = json.dumps(entry.payload)
        with self._lock:
            self._conn.execute(
                sql,
                (
                    entry.entry_id,
                    entry.entry_type.value if hasattr(entry.entry_type, "value") else str(entry.entry_type),
                    entry.session_id,
                    entry.turn_id,
                    entry.trace_id,
                    entry.source,
                    entry.timestamp,
                    payload_json,
                ),
            )
            self._conn.commit()
        self._notify_entry_listeners(entry)

    def add_entry_listener(self, listener: Callable[[TranscriptEntry], Optional[None]]) -> None:
        """Subscribe a projection listener without changing transcript ownership."""
        if listener in self._entry_listeners:
            return
        self._entry_listeners.append(listener)

    def _notify_entry_listeners(self, entry: TranscriptEntry) -> None:
        for listener in list(self._entry_listeners):
            try:
                listener(entry)
            except Exception as exc:  # pragma: no cover - listener failures must not break transcript writes
                failure = str(exc).strip() or exc.__class__.__name__
                self._listener_failures.append(failure)
                logger.warning("TranscriptStore entry listener failed: %s", failure, exc_info=True)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query_by_session(
        self, session_id: str, limit: int = 100
    ) -> list[TranscriptEntry]:
        """Return up to *limit* entries for *session_id*, newest first."""
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, trace_id, source, timestamp, payload "
            "FROM transcript_entries "
            "WHERE session_id = ? "
            "ORDER BY timestamp DESC "
            "LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, (session_id, limit)).fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    def query_history_entries(
        self,
        *,
        session_id: str,
        entry_type: str,
        limit: int = 100,
    ) -> list[TranscriptEntry]:
        """Return history entries for one session and one logical entry type."""
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, trace_id, source, timestamp, payload "
            "FROM transcript_entries "
            "WHERE session_id = ? "
            "AND COALESCE(json_extract(payload, '$.entry_type'), entry_type) = ? "
            "ORDER BY timestamp DESC "
            "LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, (session_id, entry_type, limit)).fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    def query_by_turn(self, turn_id: str) -> list[TranscriptEntry]:
        """Return all entries for *turn_id*, ordered by timestamp ASC."""
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, trace_id, source, timestamp, payload "
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
            "SELECT entry_id, entry_type, session_id, turn_id, trace_id, source, timestamp, payload "
            "FROM transcript_entries "
            "WHERE entry_type = ? "
            "ORDER BY timestamp DESC "
            "LIMIT ?"
        )
        # Use .value to ensure we query by the string value, not the enum repr
        type_val = entry_type.value if hasattr(entry_type, "value") else str(entry_type)
        with self._lock:
            rows = self._conn.execute(sql, (type_val, limit)).fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    def read_entries(
        self,
        *,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ) -> list[TranscriptEntry]:
        """Compatibility shim for BrainTranscriptStore interface.
        
        Used by KernelService._read_plugin_audit_entries to enrich snapshot artifacts.
        """
        if turn_id:
            return self.query_by_turn(turn_id)
        if session_id:
            # Note: session_id is fixed for a store instance, but we honor the filter.
            return self.query_by_session(session_id, limit=1000)
        return []

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
        """Compatibility shim for BrainTranscriptStore.write_entry.
        
        Converts parameters into a TranscriptEntry and appends it to the store.
        """
        # Resolve entry_type string value (handles both BrainTranscriptEntryType and TranscriptEntryType)
        type_str = entry_type.value if hasattr(entry_type, "value") else str(entry_type)
        
        # We try to coerce to our local enum if possible for consistency, but if not found,
        # we'll just store the string (the DB column is TEXT).
        try:
            effective_type = TranscriptEntryType(type_str)
        except (ValueError, TypeError):
            # If not in our enum, just use the string value. 
            # TranscriptEntry(entry_type=...) might type-check against Enum, but at runtime it's fine.
            effective_type = type_str  # type: ignore

        entry = TranscriptEntry(
            entry_type=effective_type,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=source,
            payload=payload,
            entry_id=entry_id or "",
            timestamp=timestamp.isoformat() if timestamp else "",
        )
        self.append(entry)

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
            "SELECT entry_id, entry_type, session_id, turn_id, trace_id, source, timestamp, payload "
            "FROM transcript_entries "
            "WHERE trace_id = ? OR payload LIKE ? "
            "ORDER BY timestamp ASC"
        )
        with self._lock:
            rows = self._conn.execute(sql, (trace_id, f'%"{trace_id}"%')).fetchall()
        
        all_entries = [_row_to_entry(tuple(r)) for r in rows]
        # Precise filtering to avoid false positives from LIKE
        return [
            e for e in all_entries 
            if isinstance(e.payload, dict) and (
                e.payload.get("trace_id") == trace_id or 
                (e.payload.get("caller_context") and e.payload["caller_context"].get("trace_id") == trace_id)
            )
        ]

    def read_entries_by_trace_prefix(self, trace_prefix: str) -> list[TranscriptEntry]:
        """Return entries whose top-level trace_id starts with the provided prefix."""
        sql = (
            "SELECT entry_id, entry_type, session_id, turn_id, trace_id, source, timestamp, payload "
            "FROM transcript_entries "
            "WHERE trace_id LIKE ? "
            "ORDER BY timestamp ASC"
        )
        with self._lock:
            rows = self._conn.execute(sql, (f"{trace_prefix}%",)).fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def build_turn_summary(self, turn_id: str) -> Optional[TurnAuditSummary]:
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
                logger.debug(
                    "Failed to parse transcript turn timestamps for turn_id=%s started_at=%s ended_at=%s",
                    turn_id,
                    started_at,
                    ended_at,
                    exc_info=True,
                )

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


class NullTranscriptStore:
    """No-op transcript adapter used when transcript persistence is disabled."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id

    def add_entry_listener(self, listener: Callable[[TranscriptEntry], Optional[None]]) -> None:
        return None

    def append(self, entry: TranscriptEntry) -> None:
        return None

    def query_by_session(self, session_id: str, limit: int = 100) -> list[TranscriptEntry]:
        return []

    def query_history_entries(
        self,
        *,
        session_id: str,
        entry_type: str,
        limit: int = 100,
    ) -> list[TranscriptEntry]:
        return []

    def query_by_turn(self, turn_id: str) -> list[TranscriptEntry]:
        return []

    def query_by_type(
        self, entry_type: TranscriptEntryType, limit: int = 50
    ) -> list[TranscriptEntry]:
        return []

    def read_entries(
        self,
        *,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ) -> list[TranscriptEntry]:
        return []

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
        return None

    def get_entries_snapshot(self) -> list[TranscriptEntry]:
        return []

    def list_entries(self, **_: Any) -> list[TranscriptEntry]:
        return []

    def read_by_turn_id(self, turn_id: str) -> list[TranscriptEntry]:
        return []

    def read_by_trace_id(self, trace_id: str) -> list[TranscriptEntry]:
        return []

    def read_entries_by_trace_prefix(self, trace_prefix: str) -> list[TranscriptEntry]:
        return []

    def build_turn_summary(self, turn_id: str) -> Optional[TurnAuditSummary]:
        return None

    def close(self) -> None:
        return None
