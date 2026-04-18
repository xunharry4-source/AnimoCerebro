"""SQLite-backed Nine-Question State Store"""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any, List
import logging

from ..contracts.kernel_service import NineQuestionStateSnapshot

logger = logging.getLogger(__name__)

QUESTION_SUMMARY_KEYS = {
    "q1": "我在哪",
    "q2": "我是谁",
    "q3": "我有什么",
    "q4": "我能做什么",
    "q5": "我被允许做什么",
    "q6": "我即使能做也不该做什么",
    "q7": "我还可以做什么",
    "q8": "我现在应该做什么",
    "q9": "我应该如何行动",
}


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

    @staticmethod
    def _isolate_question_payload(question_id: str, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        isolated = json.loads(json.dumps(payload, ensure_ascii=False))
        own_summary_key = QUESTION_SUMMARY_KEYS.get(question_id)
        if not own_summary_key:
            return isolated

        top_level = isolated.get("nine_questions")
        if isinstance(top_level, dict):
            own_value = top_level.get(own_summary_key)
            isolated["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}

        nested_context_updates = isolated.get("context_updates")
        if isinstance(nested_context_updates, dict):
            nested_summaries = nested_context_updates.get("nine_questions")
            if isinstance(nested_summaries, dict):
                own_value = nested_summaries.get(own_summary_key)
                nested_context_updates["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}

        return isolated

    @classmethod
    def _sanitize_question_snapshots(cls, snapshot_map: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(snapshot_map, dict):
            return {}

        sanitized: dict[str, dict[str, Any]] = {}
        for question_id, snapshot in snapshot_map.items():
            if not isinstance(snapshot, dict):
                continue
            normalized = json.loads(json.dumps(snapshot, ensure_ascii=False))

            result_payload = normalized.get("result")
            if isinstance(result_payload, dict):
                normalized["result"] = cls._isolate_question_payload(str(question_id), result_payload)

            context_updates = normalized.get("context_updates")
            if isinstance(context_updates, dict):
                normalized["context_updates"] = cls._isolate_question_payload(str(question_id), context_updates)

            sanitized[str(question_id)] = normalized
        return sanitized

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

        snapshot = self._row_to_snapshot(row)
        sanitized_question_snapshots = self._sanitize_question_snapshots(snapshot.question_snapshots)
        if sanitized_question_snapshots != snapshot.question_snapshots:
            snapshot.question_snapshots = sanitized_question_snapshots
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "UPDATE nine_question_states SET question_snapshots = ?, updated_at = ? WHERE session_id = ?",
                    (
                        json.dumps(sanitized_question_snapshots, ensure_ascii=False),
                        datetime.utcnow().isoformat(),
                        session_id,
                    ),
                )
                conn.commit()
        return snapshot

    async def save(self, session_id: str, state: NineQuestionStateSnapshot) -> None:
        """Save or update state"""
        sanitized_question_snapshots = self._sanitize_question_snapshots(state.question_snapshots)
        state.question_snapshots = sanitized_question_snapshots
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
                    json.dumps(sanitized_question_snapshots, ensure_ascii=False),
                    state.last_refresh_reason,
                    state.snapshot_version,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

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
