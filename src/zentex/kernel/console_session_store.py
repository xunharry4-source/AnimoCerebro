from __future__ import annotations
"""SQLite-backed Session Store"""


import sqlite3
import json
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import logging

from zentex.web_console.contracts.kernel_service import SessionSnapshot

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteSessionStore:
    """Persists SessionSnapshot to SQLite database
    
    Schema:
        Sessions table:
        - session_id (TEXT PRIMARY KEY)
        - state_id (TEXT)
        - workspace (TEXT)
        - created_at (TIMESTAMP)
        - question_drivers (JSON)
        - last_turn_id (TEXT)
        - metadata (JSON)
        - is_active (BOOLEAN)
        - updated_at (TIMESTAMP)
    """

    def __init__(self, db_path: str = "./data/sessions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema if not exists"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        state_id TEXT NOT NULL,
                        workspace TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        question_drivers TEXT NOT NULL DEFAULT '[]',
                        last_turn_id TEXT,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        updated_at TIMESTAMP NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception:
            logger.exception("Failed to initialize SQLiteSessionStore schema at %s", self.db_path)
            raise

    async def get(self, session_id: str) -> Optional[SessionSnapshot]:
        """Get session by ID"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ? AND is_active = 1",
                (session_id,),
            ).fetchone()

        if not row:
            return None

        try:
            return self._row_to_snapshot(row)
        except Exception:
            # Standard redline: never let corrupted persistence state masquerade as
            # a normal "session missing" case, and never surface it without traceback.
            logger.exception("Corrupted session snapshot in SQLiteSessionStore.get for session_id=%s", session_id)
            raise

    async def save(self, session: SessionSnapshot) -> None:
        """Save or update session"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sessions
                    (session_id, state_id, workspace, created_at, question_drivers,
                     last_turn_id, metadata, is_active, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        session.session_id,
                        session.state_id,
                        session.workspace,
                        session.created_at.isoformat(),
                        json.dumps(session.question_drivers),
                        session.last_turn_id,
                        json.dumps(session.metadata),
                        _utc_now_iso(),
                    ),
                )
                conn.commit()
        except Exception:
            # Standard redline: never let session persistence failure surface without
            # a traceback, and never let callers mistake it for a successful save.
            logger.exception("Failed to persist session snapshot for session_id=%s", session.session_id)
            raise

    async def delete(self, session_id: str) -> None:
        """Soft-delete session (mark as inactive)"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "UPDATE sessions SET is_active = 0, updated_at = ? WHERE session_id = ?",
                    (_utc_now_iso(), session_id),
                )
                conn.commit()
        except Exception:
            logger.exception("Failed to soft-delete session snapshot for session_id=%s", session_id)
            raise

    async def list_active(self) -> List[SessionSnapshot]:
        """List all active sessions"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM sessions WHERE is_active = 1 ORDER BY created_at DESC"
            ).fetchall()

        return [self._row_to_snapshot(row) for row in rows]

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> SessionSnapshot:
        """Convert database row to SessionSnapshot"""
        return SessionSnapshot(
            session_id=row["session_id"],
            state_id=row["state_id"],
            workspace=row["workspace"],
            created_at=datetime.fromisoformat(row["created_at"]),
            question_drivers=json.loads(row["question_drivers"]),
            last_turn_id=row["last_turn_id"],
            metadata=json.loads(row["metadata"]),
        )
