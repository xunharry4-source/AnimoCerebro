from __future__ import annotations

import logging

from zentex.common.database import DatabaseConnection

logger = logging.getLogger(__name__)


def ensure_task_database_schema(db: DatabaseConnection) -> None:
    """Bootstrap the shared SQLite schema when task tables are missing."""
    tasks_exists = bool(
        db.execute_scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
    )
    if not tasks_exists:
        logger.info("Bootstrapping task database schema for %s", db.db_path)
    with db.get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                parent_task_id TEXT,
                subtask_ids TEXT NOT NULL DEFAULT '[]',
                depends_on TEXT NOT NULL DEFAULT '[]',
                bundle_id TEXT,
                subtask_id TEXT,
                idempotency_key TEXT NOT NULL,
                title TEXT NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT NOT NULL DEFAULT 'medium',
                progress REAL NOT NULL DEFAULT 0.0,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                originator_id TEXT NOT NULL,
                target_id TEXT,
                remarks TEXT,
                last_error TEXT,
                execution_started_at TEXT,
                execution_finished_at TEXT,
                dispatch_plugin_id TEXT,
                execution_output TEXT,
                started_at TEXT,
                completed_at TEXT,
                deadline TEXT,
                estimated_duration INTEGER,
                tags TEXT NOT NULL DEFAULT '[]',
                contract TEXT NOT NULL DEFAULT '{}',
                metadata TEXT NOT NULL DEFAULT '{}',
                last_updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON tasks(parent_task_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_idempotency_key ON tasks(idempotency_key);
            CREATE INDEX IF NOT EXISTS idx_tasks_last_updated_at ON tasks(last_updated_at DESC);

            CREATE TABLE IF NOT EXISTS suspended_tasks (
                task_id TEXT PRIMARY KEY,
                original_status TEXT NOT NULL,
                suspension_reason TEXT NOT NULL,
                recovery_conditions TEXT NOT NULL DEFAULT '[]',
                suspension_context TEXT NOT NULL DEFAULT '{}',
                suspended_at TEXT NOT NULL,
                auto_resume_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_suspended_tasks_auto_resume_at
                ON suspended_tasks(auto_resume_at);

            CREATE TABLE IF NOT EXISTS task_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                action TEXT NOT NULL,
                operator_id TEXT NOT NULL DEFAULT 'system',
                old_status TEXT,
                new_status TEXT,
                details TEXT,
                trace_id TEXT,
                timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_task_audit_log_task_id ON task_audit_log(task_id);
            CREATE INDEX IF NOT EXISTS idx_task_audit_log_timestamp ON task_audit_log(timestamp DESC);

            CREATE TABLE IF NOT EXISTS intervention_receipts (
                idempotency_key TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                receipt TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_intervention_receipts_task_id
                ON intervention_receipts(task_id);

            CREATE TABLE IF NOT EXISTS idempotency_log (
                idempotency_key TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS task_outcomes (
                task_id TEXT PRIMARY KEY,
                trace_id TEXT,
                objective_profile TEXT,
                evaluation_profile TEXT,
                expected_outcome TEXT,
                success_criteria TEXT,
                acceptance_conditions TEXT,
                risk_assessment TEXT,
                actual_outcome TEXT,
                deviation_report TEXT,
                verification_result TEXT,
                overall_passed INTEGER,
                confidence_score REAL,
                user_feedback TEXT,
                written_back_to_reflection INTEGER NOT NULL DEFAULT 0,
                reflection_id TEXT,
                written_back_to_learning INTEGER NOT NULL DEFAULT 0,
                learning_trace_id TEXT,
                written_back_to_memory INTEGER NOT NULL DEFAULT 0,
                memory_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_task_outcomes_trace ON task_outcomes(trace_id);
            CREATE INDEX IF NOT EXISTS idx_task_outcomes_passed ON task_outcomes(overall_passed, created_at);
            CREATE INDEX IF NOT EXISTS idx_task_outcomes_completed ON task_outcomes(completed_at);
            """
        )
        _ensure_tasks_columns(conn)
        _ensure_intervention_receipt_columns(conn)
        _ensure_task_outcome_columns(conn)


def _ensure_tasks_columns(conn) -> None:
    """Apply lightweight task-table migrations for existing local databases."""
    rows = conn.execute("PRAGMA table_info(tasks)").fetchall()
    existing = {str(row[1]) for row in rows}
    migrations = {
        "attempt_count": "ALTER TABLE tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
        "last_error": "ALTER TABLE tasks ADD COLUMN last_error TEXT",
        "execution_started_at": "ALTER TABLE tasks ADD COLUMN execution_started_at TEXT",
        "execution_finished_at": "ALTER TABLE tasks ADD COLUMN execution_finished_at TEXT",
        "dispatch_plugin_id": "ALTER TABLE tasks ADD COLUMN dispatch_plugin_id TEXT",
        "execution_output": "ALTER TABLE tasks ADD COLUMN execution_output TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            logger.info("Adding missing tasks.%s column", column)
            conn.execute(sql)


def _ensure_intervention_receipt_columns(conn) -> None:
    """Apply lightweight migrations for intervention receipts on existing databases."""
    rows = conn.execute("PRAGMA table_info(intervention_receipts)").fetchall()
    if not rows:
        return
    existing = {str(row[1]) for row in rows}
    migrations = {
        "action": "ALTER TABLE intervention_receipts ADD COLUMN action TEXT",
        "new_status": "ALTER TABLE intervention_receipts ADD COLUMN new_status TEXT",
        "remarks": "ALTER TABLE intervention_receipts ADD COLUMN remarks TEXT",
        "operator_id": "ALTER TABLE intervention_receipts ADD COLUMN operator_id TEXT",
        "recorded_at": "ALTER TABLE intervention_receipts ADD COLUMN recorded_at TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            logger.info("Adding missing intervention_receipts.%s column", column)
            conn.execute(sql)


def _ensure_task_outcome_columns(conn) -> None:
    """Apply lightweight migrations for task outcome records."""
    rows = conn.execute("PRAGMA table_info(task_outcomes)").fetchall()
    if not rows:
        return
    existing = {str(row[1]) for row in rows}
    migrations = {
        "objective_profile": "ALTER TABLE task_outcomes ADD COLUMN objective_profile TEXT",
        "evaluation_profile": "ALTER TABLE task_outcomes ADD COLUMN evaluation_profile TEXT",
        "expected_outcome": "ALTER TABLE task_outcomes ADD COLUMN expected_outcome TEXT",
        "success_criteria": "ALTER TABLE task_outcomes ADD COLUMN success_criteria TEXT",
        "acceptance_conditions": "ALTER TABLE task_outcomes ADD COLUMN acceptance_conditions TEXT",
        "risk_assessment": "ALTER TABLE task_outcomes ADD COLUMN risk_assessment TEXT",
        "actual_outcome": "ALTER TABLE task_outcomes ADD COLUMN actual_outcome TEXT",
        "deviation_report": "ALTER TABLE task_outcomes ADD COLUMN deviation_report TEXT",
        "verification_result": "ALTER TABLE task_outcomes ADD COLUMN verification_result TEXT",
        "overall_passed": "ALTER TABLE task_outcomes ADD COLUMN overall_passed INTEGER",
        "confidence_score": "ALTER TABLE task_outcomes ADD COLUMN confidence_score REAL",
        "user_feedback": "ALTER TABLE task_outcomes ADD COLUMN user_feedback TEXT",
        "written_back_to_reflection": "ALTER TABLE task_outcomes ADD COLUMN written_back_to_reflection INTEGER NOT NULL DEFAULT 0",
        "reflection_id": "ALTER TABLE task_outcomes ADD COLUMN reflection_id TEXT",
        "written_back_to_learning": "ALTER TABLE task_outcomes ADD COLUMN written_back_to_learning INTEGER NOT NULL DEFAULT 0",
        "learning_trace_id": "ALTER TABLE task_outcomes ADD COLUMN learning_trace_id TEXT",
        "written_back_to_memory": "ALTER TABLE task_outcomes ADD COLUMN written_back_to_memory INTEGER NOT NULL DEFAULT 0",
        "memory_id": "ALTER TABLE task_outcomes ADD COLUMN memory_id TEXT",
        "created_at": "ALTER TABLE task_outcomes ADD COLUMN created_at TEXT",
        "completed_at": "ALTER TABLE task_outcomes ADD COLUMN completed_at TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            logger.info("Adding missing task_outcomes.%s column", column)
            conn.execute(sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_outcomes_reflection ON task_outcomes(reflection_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_outcomes_learning ON task_outcomes(learning_trace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_outcomes_memory ON task_outcomes(memory_id)")
