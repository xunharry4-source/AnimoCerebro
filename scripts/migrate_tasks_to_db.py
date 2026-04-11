#!/usr/bin/env python3
"""
Migrate task data from JSON files to SQLite database.

This script reads existing task data from JSON persistence files
and migrates them to the new SQLite database schema.

Usage:
    python scripts/migrate_tasks_to_db.py [--dry-run] [--backup]
"""

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zentex.common.database import DatabaseConnection
from zentex.tasks.dao import (
    TaskDAO,
    SuspendedTaskDAO,
    TaskAuditLogDAO,
    InterventionReceiptDAO,
    IdempotencyLogDAO,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_tasks_to_db(
    json_storage_path: str,
    db_path: str,
    dry_run: bool = False,
    backup: bool = True
) -> Dict[str, Any]:
    """
    Migrate task data from JSON files to SQLite database.
    
    Args:
        json_storage_path: Path to JSON storage directory
        db_path: Path to SQLite database
        dry_run: If True, only report what would be migrated
        backup: If True, create backup of JSON files
    
    Returns:
        Migration statistics
    """
    stats = {
        'tasks_migrated': 0,
        'suspended_tasks_migrated': 0,
        'interventions_migrated': 0,
        'idempotency_records_migrated': 0,
        'errors': [],
        'started_at': datetime.now().isoformat(),
    }
    
    json_path = Path(json_storage_path)
    db = DatabaseConnection(db_path)
    
    # Initialize DAOs
    task_dao = TaskDAO(db)
    suspended_dao = SuspendedTaskDAO(db)
    audit_dao = TaskAuditLogDAO(db)
    intervention_dao = InterventionReceiptDAO(db)
    idempotency_dao = IdempotencyLogDAO(db)
    
    try:
        # Load JSON data
        tasks_file = json_path / "tasks.json"
        suspended_file = json_path / "suspended_tasks.json"
        interventions_file = json_path / "interventions.json"
        idempotency_file = json_path / "idempotency.json"
        
        # Backup if requested
        if backup and not dry_run:
            backup_dir = json_path / f"backup_before_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(exist_ok=True)
            for f in [tasks_file, suspended_file, interventions_file, idempotency_file]:
                if f.exists():
                    shutil.copy2(f, backup_dir / f.name)
            logger.info(f"Backup created at: {backup_dir}")
        
        # Migrate tasks
        if tasks_file.exists():
            logger.info("Migrating tasks...")
            with open(tasks_file, 'r', encoding='utf-8') as f:
                tasks_data = json.load(f)
            
            for task_id, task_dict in tasks_data.items():
                try:
                    if not dry_run:
                        success = task_dao.create_task(task_dict)
                        if success:
                            stats['tasks_migrated'] += 1
                            # Log creation event
                            audit_dao.log_action(
                                task_id=task_id,
                                action="TASK_MIGRATED",
                                operator_id="migration_script",
                                details={"source": "json_file"}
                            )
                    else:
                        stats['tasks_migrated'] += 1
                        logger.debug(f"Would migrate task: {task_id}")
                except Exception as e:
                    error_msg = f"Failed to migrate task {task_id}: {e}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
        else:
            logger.warning(f"Tasks file not found: {tasks_file}")
        
        # Migrate suspended tasks
        if suspended_file.exists():
            logger.info("Migrating suspended tasks...")
            with open(suspended_file, 'r', encoding='utf-8') as f:
                suspended_data = json.load(f)
            
            for task_id, suspension_dict in suspended_data.items():
                try:
                    if not dry_run:
                        suspension_dict['task_id'] = task_id
                        success = suspended_dao.suspend_task(suspension_dict)
                        if success:
                            stats['suspended_tasks_migrated'] += 1
                    else:
                        stats['suspended_tasks_migrated'] += 1
                except Exception as e:
                    error_msg = f"Failed to migrate suspended task {task_id}: {e}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
        else:
            logger.warning(f"Suspended tasks file not found: {suspended_file}")
        
        # Migrate interventions
        if interventions_file.exists():
            logger.info("Migrating interventions...")
            with open(interventions_file, 'r', encoding='utf-8') as f:
                interventions_data = json.load(f)
            
            for key, receipt_dict in interventions_data.items():
                try:
                    if not dry_run:
                        receipt_dict['idempotency_key'] = key
                        success = intervention_dao.record_intervention(receipt_dict)
                        if success:
                            stats['interventions_migrated'] += 1
                    else:
                        stats['interventions_migrated'] += 1
                except Exception as e:
                    error_msg = f"Failed to migrate intervention {key}: {e}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
        else:
            logger.warning(f"Interventions file not found: {interventions_file}")
        
        # Migrate idempotency log
        if idempotency_file.exists():
            logger.info("Migrating idempotency log...")
            with open(idempotency_file, 'r', encoding='utf-8') as f:
                idempotency_data = json.load(f)
            
            for key, task_id in idempotency_data.items():
                try:
                    if not dry_run:
                        success = idempotency_dao.record_idempotency(key, task_id)
                        if success:
                            stats['idempotency_records_migrated'] += 1
                    else:
                        stats['idempotency_records_migrated'] += 1
                except Exception as e:
                    error_msg = f"Failed to migrate idempotency key {key}: {e}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
        else:
            logger.warning(f"Idempotency file not found: {idempotency_file}")
        
        stats['completed_at'] = datetime.now().isoformat()
        logger.info(f"Migration completed: {stats}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        stats['errors'].append(str(e))
        return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate tasks from JSON to SQLite")
    parser.add_argument("--json-path", default=".zentex/runtime/tasks", help="JSON storage path")
    parser.add_argument("--db-path", default="runtime/data/zentex_core.db", help="Database path")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Task Data Migration: JSON → SQLite")
    print("=" * 60)
    print(f"JSON path: {args.json_path}")
    print(f"Database path: {args.db_path}")
    print(f"Dry run: {args.dry_run}")
    print(f"Backup: {not args.no_backup}")
    print("=" * 60)
    print()
    
    stats = migrate_tasks_to_db(
        json_storage_path=args.json_path,
        db_path=args.db_path,
        dry_run=args.dry_run,
        backup=not args.no_backup
    )
    
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"✅ Tasks migrated: {stats['tasks_migrated']}")
    print(f"✅ Suspended tasks migrated: {stats['suspended_tasks_migrated']}")
    print(f"✅ Interventions migrated: {stats['interventions_migrated']}")
    print(f"✅ Idempotency records migrated: {stats['idempotency_records_migrated']}")
    print(f"❌ Errors: {len(stats['errors'])}")
    
    if stats['errors']:
        print("\nErrors encountered:")
        for error in stats['errors'][:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(stats['errors']) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more errors")
    
    print("=" * 60)
    
    # Exit with error code if there were errors
    sys.exit(1 if stats['errors'] else 0)
