#!/usr/bin/env python3
"""
Database migration script for Zentex persistent storage.

This script applies schema migrations to the SQLite database and ensures
the database is ready for use by the application.

Usage:
    python scripts/migrate_database.py [--db-path PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_current_version(db_path: Path) -> int:
    """Get current schema version from database."""
    if not db_path.exists():
        return 0
    
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if not cursor.fetchone():
            return 0
        
        cursor = conn.execute("SELECT MAX(version) FROM schema_version")
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0
    finally:
        conn.close()


def apply_migration(db_path: Path, sql_file: Path, version: int) -> bool:
    """Apply a migration SQL file to the database."""
    logger.info(f"Applying migration v{version}: {sql_file.name}")
    
    if not sql_file.exists():
        logger.error(f"Migration file not found: {sql_file}")
        return False
    
    conn = sqlite3.connect(str(db_path))
    try:
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Read SQL file
        sql_content = sql_file.read_text(encoding='utf-8')
        
        # Execute all statements
        conn.executescript(sql_content)
        
        # Update version (use INSERT OR IGNORE to avoid duplicate key errors)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description, applied_by) VALUES (?, ?, ?)",
            (version, f"Applied from {sql_file.name}", "migration_script")
        )
        conn.commit()
        
        logger.info(f"Successfully applied migration v{version}")
        return True
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to apply migration v{version}: {e}", exc_info=True)
        return False
    finally:
        conn.close()


def migrate_database(db_path: Path, dry_run: bool = False) -> bool:
    """
    Run all pending migrations on the database.
    
    Args:
        db_path: Path to the SQLite database file
        dry_run: If True, only show what would be done without applying
        
    Returns:
        True if migration succeeded, False otherwise
    """
    logger.info(f"Starting database migration for: {db_path}")
    
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get current version
    current_version = get_current_version(db_path)
    logger.info(f"Current schema version: {current_version}")
    
    # Find migration files
    migrations_dir = Path(__file__).parent.parent / "runtime" / "data"
    migration_files = sorted(migrations_dir.glob("schema_v*.sql"))
    
    if not migration_files:
        logger.warning("No migration files found!")
        return False
    
    # Apply pending migrations
    success = True
    for migration_file in migration_files:
        # Extract version from filename (e.g., schema_v1.sql -> 1)
        try:
            version = int(migration_file.stem.replace("schema_v", ""))
        except ValueError:
            logger.warning(f"Skipping invalid migration file: {migration_file.name}")
            continue
        
        if version <= current_version:
            logger.info(f"Skipping already applied migration v{version}")
            continue
        
        if dry_run:
            logger.info(f"[DRY RUN] Would apply migration v{version}: {migration_file.name}")
            continue
        
        if not apply_migration(db_path, migration_file, version):
            logger.error(f"Migration failed at v{version}")
            success = False
            break
    
    if success:
        new_version = get_current_version(db_path)
        logger.info(f"Migration completed. New schema version: {new_version}")
    
    return success


def verify_database(db_path: Path) -> bool:
    """Verify database integrity after migration."""
    logger.info(f"Verifying database integrity: {db_path}")
    
    if not db_path.exists():
        logger.error("Database file does not exist")
        return False
    
    conn = sqlite3.connect(str(db_path))
    try:
        # Check integrity
        cursor = conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        if result[0] != "ok":
            logger.error(f"Database integrity check failed: {result[0]}")
            return False
        
        # Check required tables exist
        required_tables = [
            'agents', 'agent_audit_log',
            'mcp_servers', 'mcp_tools', 'mcp_execution_records',
            'cli_tools', 'cli_execution_history', 'cli_tool_credit_scores',
            'task_agent_mapping', 'task_cli_mapping', 'task_mcp_mapping',
            'schema_version'
        ]
        
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        missing_tables = set(required_tables) - existing_tables
        if missing_tables:
            logger.error(f"Missing required tables: {missing_tables}")
            return False
        
        # Check views exist
        required_views = [
            'v_agent_full_info',
            'v_mcp_server_full_info',
            'v_cli_tool_stats'
        ]
        
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
        existing_views = {row[0] for row in cursor.fetchall()}
        
        missing_views = set(required_views) - existing_views
        if missing_views:
            logger.error(f"Missing required views: {missing_views}")
            return False
        
        logger.info("Database verification passed")
        return True
        
    except Exception as e:
        logger.error(f"Database verification failed: {e}", exc_info=True)
        return False
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate Zentex database schema")
    parser.add_argument(
        "--db-path",
        type=str,
        default="runtime/data/zentex_core.db",
        help="Path to SQLite database file (default: runtime/data/zentex_core.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without applying changes"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify database without applying migrations"
    )
    
    args = parser.parse_args()
    db_path = Path(args.db_path)
    
    if args.verify_only:
        success = verify_database(db_path)
        sys.exit(0 if success else 1)
    
    success = migrate_database(db_path, dry_run=args.dry_run)
    
    if success and not args.dry_run:
        verify_success = verify_database(db_path)
        if not verify_success:
            logger.error("Migration succeeded but verification failed!")
            sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
