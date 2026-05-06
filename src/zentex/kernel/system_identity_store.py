from __future__ import annotations

"""Core-owned single system identity store."""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SystemIdentityStore:
    """SQLite-backed store for the single user-configured system role."""

    _ROW_ID = 1

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_identity (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    role_name TEXT NOT NULL,
                    mission TEXT,
                    core_values TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()
            logger.info("System identity database initialized at %s", self.db_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_core_values(core_values: Any) -> list[str]:
        if isinstance(core_values, list):
            return [str(item).strip() for item in core_values if str(item).strip()]
        if isinstance(core_values, str):
            return [line.strip() for line in core_values.splitlines() if line.strip()]
        return []

    def get_identity(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM system_identity WHERE id = ?",
                (self._ROW_ID,),
            ).fetchone()
            if row is None:
                return {
                    "role_name": "",
                    "identity_role": "",
                    "mission": "",
                    "core_values": [],
                    "user_configured": False,
                    "identity_kernel_snapshot": {},
                }
            core_values = self._decode_core_values(row["core_values"])
            role_name = str(row["role_name"] or "").strip()
            mission = str(row["mission"] or "").strip()
            snapshot = {
                "role_name": role_name,
                "identity_role": role_name,
                "mission": mission,
                "meta_motivation": mission,
                "meta_drives": [mission] if mission else [],
                "core_values": core_values,
                "values_prohibition": " / ".join(core_values),
                "value_vetoes": core_values,
                "non_bypassable_constraints": core_values,
                "source": "user_system_identity_store",
                "user_configured": True,
            }
            return {
                "role_name": role_name,
                "identity_role": role_name,
                "mission": mission,
                "core_values": core_values,
                "user_configured": True,
                "source": "user_system_identity_store",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "identity_kernel_snapshot": snapshot,
            }

    def update_identity(
        self,
        *,
        role_name: str,
        mission: str = "",
        core_values: list[str] | str | None = None,
    ) -> dict[str, Any]:
        normalized_role = str(role_name or "").strip()
        if not normalized_role:
            raise ValueError("role_name is required")
        normalized_mission = str(mission or "").strip()
        normalized_values = self._normalize_core_values(core_values)
        now = self._now()
        with self._lock:
            existing = self._conn.execute(
                "SELECT created_at FROM system_identity WHERE id = ?",
                (self._ROW_ID,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            self._conn.execute(
                """
                INSERT INTO system_identity
                    (id, role_name, mission, core_values, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role_name = excluded.role_name,
                    mission = excluded.mission,
                    core_values = excluded.core_values,
                    updated_at = excluded.updated_at
                """,
                (
                    self._ROW_ID,
                    normalized_role,
                    normalized_mission,
                    json.dumps(normalized_values, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )
            self._conn.commit()
            return self.get_identity()

    def reset_identity(self) -> dict[str, Any]:
        with self._lock:
            self._conn.execute("DELETE FROM system_identity WHERE id = ?", (self._ROW_ID,))
            self._conn.commit()
            return self.get_identity()

    @staticmethod
    def _decode_core_values(raw: Any) -> list[str]:
        if raw in (None, ""):
            return []
        try:
            parsed = json.loads(str(raw))
        except json.JSONDecodeError:
            return [str(raw).strip()] if str(raw).strip() else []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return []

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
