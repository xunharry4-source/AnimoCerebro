"""
Workspace Storage / 工作区存储层

SQLite-based persistence layer for workspace configurations.
为工作区配置提供 SQLite 持久化层。
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from zentex.web_console.models.workspace import WorkspaceConfig

logger = logging.getLogger(__name__)


class WorkspaceStore:
    """
    SQLite-based manager for workspace configurations.
    
    Handles CRUD operations, validation, and persistence for workspaces.
    基于 SQLite 的工作区配置存储，处理 CRUD、验证和持久化。
    """

    def __init__(self, db_path: str | Path):
        """
        Initialize workspace store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # CRUD helpers call other lock-protected methods (for example
        # add_workspace() -> get_workspace()). A non-reentrant lock deadlocks
        # those flows under normal API usage.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            
            # Create workspaces table
            self._conn.execute("""
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
            """)
            
            # Migrate existing table: add new columns if they don't exist
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
            
            # Create indexes
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_default ON workspaces(is_default)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_path ON workspaces(path)")
            
            self._conn.commit()
            logger.info(f"Workspace database initialized at {self.db_path}")

    def _get_now(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def add_workspace(self, config: WorkspaceConfig) -> WorkspaceConfig:
        """
        Add a new workspace.
        
        Args:
            config: WorkspaceConfig object (id should be None)
            
        Returns:
            WorkspaceConfig with assigned id
            
        Raises:
            ValueError: If workspace name or path already exists
        """
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
                    )
                )
                self._conn.commit()
                
                # Retrieve the inserted record
                inserted_id = cursor.lastrowid
                return self.get_workspace(inserted_id)
                
            except sqlite3.IntegrityError as e:
                logger.error(f"Integrity error adding workspace: {e}")
                if "UNIQUE constraint failed: workspaces.name" in str(e):
                    raise ValueError(f"Workspace name '{config.name}' already exists") from e
                elif "UNIQUE constraint failed: workspaces.path" in str(e):
                    raise ValueError(f"Workspace path '{config.path}' already exists") from e
                raise

    def list_workspaces(self) -> List[WorkspaceConfig]:
        """
        List all workspaces.
        
        Returns:
            List of WorkspaceConfig objects
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM workspaces ORDER BY is_default DESC, created_at DESC"
            )
            rows = cursor.fetchall()
            
            return [self._row_to_config(row) for row in rows]

    def get_workspace(self, workspace_id: int) -> Optional[WorkspaceConfig]:
        """
        Get a single workspace by ID.
        
        Args:
            workspace_id: Workspace ID
            
        Returns:
            WorkspaceConfig or None if not found
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM workspaces WHERE id = ?",
                (workspace_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_config(row)
            return None

    def get_workspace_by_path(self, path: str) -> Optional[WorkspaceConfig]:
        """
        Get a workspace by path.
        
        Args:
            path: Workspace path
            
        Returns:
            WorkspaceConfig or None if not found
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM workspaces WHERE path = ?",
                (str(Path(path).resolve()),)
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_config(row)
            return None

    def update_workspace(self, workspace_id: int, config: WorkspaceConfig) -> Optional[WorkspaceConfig]:
        """
        Update an existing workspace.
        
        Args:
            workspace_id: Workspace ID to update
            config: Updated WorkspaceConfig (id field is ignored)
            
        Returns:
            Updated WorkspaceConfig or None if not found
            
        Raises:
            ValueError: If new name or path conflicts with existing workspaces
        """
        with self._lock:
            try:
                # Check if workspace exists
                if not self.get_workspace(workspace_id):
                    return None
                
                # Check for conflicts on name and path
                existing = self._conn.execute(
                    "SELECT id FROM workspaces WHERE (name = ? OR path = ?) AND id != ?",
                    (config.name, config.path, workspace_id)
                ).fetchone()
                
                if existing:
                    raise ValueError(f"Name or path conflicts with another workspace")
                
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
                    )
                )
                self._conn.commit()
                
                return self.get_workspace(workspace_id)
                
            except sqlite3.Error as e:
                logger.error(f"Database error updating workspace: {e}")
                raise

    def delete_workspace(self, workspace_id: int) -> bool:
        """
        Delete a workspace.
        
        Args:
            workspace_id: Workspace ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM workspaces WHERE id = ?",
                (workspace_id,)
            )
            self._conn.commit()
            
            return cursor.rowcount > 0

    def set_default_workspace(self, workspace_id: int) -> bool:
        """
        Set a workspace as the default.
        
        Args:
            workspace_id: Workspace ID to set as default
            
        Returns:
            True if successful, False if workspace not found
        """
        with self._lock:
            # Check workspace exists
            if not self.get_workspace(workspace_id):
                return False
            
            # Clear other defaults
            self._conn.execute("UPDATE workspaces SET is_default = 0")
            
            # Set this one as default
            self._conn.execute(
                "UPDATE workspaces SET is_default = 1, updated_at = ? WHERE id = ?",
                (self._get_now(), workspace_id)
            )
            self._conn.commit()
            
            return True

    def get_default_workspace(self) -> Optional[WorkspaceConfig]:
        """
        Get the default workspace.
        
        Returns:
            Default WorkspaceConfig or None if not found
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM workspaces WHERE is_default = 1 LIMIT 1"
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_config(row)
            return None

    def count_workspaces(self) -> int:
        """
        Get total number of workspaces.
        
        Returns:
            Number of workspaces
        """
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(*) as count FROM workspaces")
            result = cursor.fetchone()
            return result[0] if result else 0

    def _row_to_config(self, row: sqlite3.Row) -> WorkspaceConfig:
        """Convert SQLite row to WorkspaceConfig."""
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

    def close(self):
        """Close database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
