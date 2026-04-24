from __future__ import annotations

"""Core-owned workspace metadata store."""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from zentex.web_console.models.workspace import WorkspaceConfig

logger = logging.getLogger(__name__)


class WorkspaceStore:
    """SQLite-backed workspace metadata store owned by the core runtime."""

    def __init__(self, db_path: Union[str, Path]):
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
                CREATE TABLE IF NOT EXISTS workspaces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL UNIQUE,
                    description TEXT,
                    is_default BOOLEAN DEFAULT 0,
                    role TEXT,
                    role_description TEXT,
                    forbidden_actions TEXT,
                    task_goals TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            cursor = self._conn.execute("PRAGMA table_info(workspaces)")
            columns = {row[1] for row in cursor.fetchall()}
            if "role" not in columns:
                logger.info("Migrating: Adding 'role' column to workspaces table")
                self._conn.execute("ALTER TABLE workspaces ADD COLUMN role TEXT")
            if "role_description" not in columns:
                logger.info("Migrating: Adding 'role_description' column to workspaces table")
                self._conn.execute("ALTER TABLE workspaces ADD COLUMN role_description TEXT")
            if "forbidden_actions" not in columns:
                logger.info("Migrating: Adding 'forbidden_actions' column to workspaces table")
                self._conn.execute("ALTER TABLE workspaces ADD COLUMN forbidden_actions TEXT")
            if "task_goals" not in columns:
                logger.info("Migrating: Adding 'task_goals' column to workspaces table")
                self._conn.execute("ALTER TABLE workspaces ADD COLUMN task_goals TEXT")

            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_default ON workspaces(is_default)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_path ON workspaces(path)")
            self._conn.commit()
            logger.info("Workspace database initialized at %s", self.db_path)

    def _get_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_workspace(self, config: WorkspaceConfig) -> WorkspaceConfig:
        with self._lock:
            try:
                cursor = self._conn.execute(
                    """
                    INSERT INTO workspaces
                    (name, path, description, is_default, role, role_description, forbidden_actions, task_goals, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        config.name,
                        config.path,
                        config.description,
                        1 if config.is_default else 0,
                        config.role,
                        config.role_description,
                        config.forbidden_actions,
                        config.task_goals,
                        self._get_now(),
                        self._get_now(),
                    ),
                )
                self._conn.commit()
                return self.get_workspace(cursor.lastrowid)
            except sqlite3.IntegrityError as exc:
                logger.error("Integrity error adding workspace: %s", exc)
                if "UNIQUE constraint failed: workspaces.name" in str(exc):
                    raise ValueError(f"Workspace name '{config.name}' already exists") from exc
                if "UNIQUE constraint failed: workspaces.path" in str(exc):
                    raise ValueError(f"Workspace path '{config.path}' already exists") from exc
                raise

    def list_workspaces(self) -> list[WorkspaceConfig]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM workspaces ORDER BY is_default DESC, created_at DESC")
            return [self._row_to_config(row) for row in cursor.fetchall()]

    def get_workspace(self, workspace_id: int) -> Optional[WorkspaceConfig]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
            row = cursor.fetchone()
            return self._row_to_config(row) if row else None

    def get_workspace_by_path(self, path: str) -> Optional[WorkspaceConfig]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM workspaces WHERE path = ?", (str(Path(path).resolve()),))
            row = cursor.fetchone()
            return self._row_to_config(row) if row else None

    def update_workspace(self, workspace_id: int, config: WorkspaceConfig) -> Optional[WorkspaceConfig]:
        with self._lock:
            if not self.get_workspace(workspace_id):
                return None
            existing = self._conn.execute(
                "SELECT id FROM workspaces WHERE (name = ? OR path = ?) AND id != ?",
                (config.name, config.path, workspace_id),
            ).fetchone()
            if existing:
                raise ValueError("Name or path conflicts with another workspace")
            self._conn.execute(
                """
                UPDATE workspaces
                SET name = ?, path = ?, description = ?, is_default = ?, role = ?, role_description = ?, forbidden_actions = ?, task_goals = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    config.name,
                    config.path,
                    config.description,
                    1 if config.is_default else 0,
                    config.role,
                    config.role_description,
                    config.forbidden_actions,
                    config.task_goals,
                    self._get_now(),
                    workspace_id,
                ),
            )
            self._conn.commit()
            return self.get_workspace(workspace_id)

    def delete_workspace(self, workspace_id: int) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def set_default_workspace(self, workspace_id: int) -> bool:
        with self._lock:
            if not self.get_workspace(workspace_id):
                return False
            self._conn.execute("UPDATE workspaces SET is_default = 0")
            self._conn.execute(
                "UPDATE workspaces SET is_default = 1, updated_at = ? WHERE id = ?",
                (self._get_now(), workspace_id),
            )
            self._conn.commit()
            return True

    def get_default_workspace(self) -> Optional[WorkspaceConfig]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM workspaces WHERE is_default = 1 LIMIT 1")
            row = cursor.fetchone()
            return self._row_to_config(row) if row else None

    def count_workspaces(self) -> int:
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(*) as count FROM workspaces")
            result = cursor.fetchone()
            return result[0] if result else 0

    def _row_to_config(self, row: sqlite3.Row) -> WorkspaceConfig:
        return WorkspaceConfig(
            id=row["id"],
            name=row["name"],
            path=row["path"],
            description=row["description"],
            is_default=bool(row["is_default"]),
            role=row["role"],
            role_description=row["role_description"],
            forbidden_actions=row["forbidden_actions"],
            task_goals=row["task_goals"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
