"""SQLite-backed Nine-Question State Store"""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List
import logging

from ..contracts.kernel_service import NineQuestionStateSnapshot

logger = logging.getLogger(__name__)


class SQLiteStateStore:
    """Persists NineQuestionStateSnapshot to SQLite database
    
    Schema:
        NineQuestionStates table:
        - session_id (TEXT PRIMARY KEY)
        - version (INTEGER)
        - revision (INTEGER)
        - dirty_questions (JSON array)
        - last_refresh_reason (TEXT)
        - snapshot_version (INTEGER)
        - updated_at (TIMESTAMP)
    """

    def __init__(self, db_path: str = "./data/sessions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema if not exists"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nine_question_states (
                    session_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 0,
                    dirty_questions TEXT NOT NULL DEFAULT '[]',
                    question_snapshots TEXT NOT NULL DEFAULT '{}',
                    last_refresh_reason TEXT,
                    snapshot_version INTEGER NOT NULL DEFAULT 9,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(nine_question_states)").fetchall()
            }
            if "question_snapshots" not in columns:
                conn.execute(
                    "ALTER TABLE nine_question_states ADD COLUMN question_snapshots TEXT NOT NULL DEFAULT '{}'"
                )
            conn.commit()

    async def get(self, session_id: str) -> NineQuestionStateSnapshot | None:
        """Get state by session ID"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM nine_question_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if not row:
            return None

        return self._row_to_snapshot(row)

    async def save(self, session_id: str, state: NineQuestionStateSnapshot) -> None:
        """Save or update state"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO nine_question_states
                (session_id, version, revision, dirty_questions, question_snapshots, last_refresh_reason,
                 snapshot_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    state.version,
                    state.revision,
                    json.dumps(state.dirty_questions),
                    json.dumps(state.question_snapshots),
                    state.last_refresh_reason,
                    state.snapshot_version,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    async def get_latest_populated(self) -> NineQuestionStateSnapshot | None:
        """Return the most recently updated non-empty snapshot, if any."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM nine_question_states
                WHERE question_snapshots IS NOT NULL
                  AND question_snapshots != '{}'
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()

        if not row:
            return None

        return self._row_to_snapshot(row)

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> NineQuestionStateSnapshot:
        """Convert database row to NineQuestionStateSnapshot"""
        return NineQuestionStateSnapshot(
            version=row["version"],
            revision=row["revision"],
            dirty_questions=json.loads(row["dirty_questions"]),
            question_snapshots=json.loads(row["question_snapshots"] or "{}"),
            last_refresh_reason=row["last_refresh_reason"],
            snapshot_version=row["snapshot_version"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
