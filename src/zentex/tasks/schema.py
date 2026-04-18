from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from zentex.common.database import DatabaseConnection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column definitions that must exist in the tasks table.
# Each entry: (column_name, sql_type_and_default)
# ---------------------------------------------------------------------------
_TASKS_REQUIRED_COLUMNS: list[tuple[str, str]] = [
    # Core execution result — written by TaskExecutionWorker after plugin completes
    ("execution_output", "TEXT DEFAULT NULL"),          # JSON blob
    # Which plugin actually ran the task
    ("dispatch_plugin_id", "TEXT DEFAULT NULL"),
    # Execution timestamps
    ("execution_started_at", "TIMESTAMP DEFAULT NULL"),
    ("execution_finished_at", "TIMESTAMP DEFAULT NULL"),
    # Last error message for this task (overwritten on each attempt)
    ("last_error", "TEXT DEFAULT NULL"),
    # How many times this task has been attempted
    ("attempt_count", "INTEGER DEFAULT 0"),
]


def ensure_task_database_schema(db: DatabaseConnection) -> None:
    """Bootstrap the shared SQLite schema when task tables are missing.

    Safe to call multiple times — it is idempotent.
    After the initial table creation it also runs :func:`migrate_task_schema`
    to add any columns that were introduced after the initial schema version.
    """
    if not db.execute_scalar(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tasks'"
    ):
        _apply_initial_schema(db)

    # Always run migration — it is a no-op for columns that already exist.
    migrate_task_schema(db)


def migrate_task_schema(db: DatabaseConnection) -> None:
    """Add missing columns to the *tasks* table without dropping existing data.

    Uses ``PRAGMA table_info`` to discover the current column set, then issues
    ``ALTER TABLE … ADD COLUMN`` only for columns that are absent.  This makes
    the migration safe to run on both fresh and existing databases.
    """
    existing_columns: set[str] = {
        str(row["name"])
        for row in db.execute_query("PRAGMA table_info(tasks)")
    }

    added: list[str] = []
    for col_name, col_def in _TASKS_REQUIRED_COLUMNS:
        if col_name not in existing_columns:
            try:
                db.execute_update(
                    f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def}"
                )
                added.append(col_name)
                logger.info("tasks table: added column '%s'", col_name)
            except Exception as exc:  # pragma: no cover — race condition guard
                logger.warning(
                    "tasks table: could not add column '%s': %s", col_name, exc
                )

    if added:
        logger.info(
            "tasks schema migration complete — %d column(s) added: %s",
            len(added),
            ", ".join(added),
        )
    else:
        logger.debug("tasks schema migration: no changes needed")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _apply_initial_schema(db: DatabaseConnection) -> None:
    """Run schema_v1 + schema_v2_tasks SQL files to create all tables."""
    repo_root = Path(__file__).resolve().parents[3]
    schema_v1_path = repo_root / "runtime" / "data" / "schema_v1.sql"
    schema_v2_tasks_path = repo_root / "runtime" / "data" / "schema_v2_tasks.sql"

    if not schema_v1_path.exists():
        raise FileNotFoundError(f"Missing core schema file: {schema_v1_path}")
    if not schema_v2_tasks_path.exists():
        raise FileNotFoundError(f"Missing task schema file: {schema_v2_tasks_path}")

    logger.info("Bootstrapping task database schema for %s", db.db_path)
    with db.get_connection() as conn:
        conn.executescript(schema_v1_path.read_text(encoding="utf-8"))
        conn.executescript(schema_v2_tasks_path.read_text(encoding="utf-8"))
