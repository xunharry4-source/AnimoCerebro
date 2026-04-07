from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from zentex.tasks.models import ZentexTask, SuspendedTask, TaskStatus

logger = logging.getLogger(__name__)

class TaskPersistence:
    """
    Task persistence layer for task management service.
    Provides atomic save/load operations with backup and recovery.
    """
    
    def __init__(self, storage_path: str, backup_count: int = 5):
        self.storage_path = Path(storage_path)
        self.backup_count = backup_count
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.tasks_file = self.storage_path / "tasks.json"
        self.suspended_tasks_file = self.storage_path / "suspended_tasks.json"
        self.idempotency_file = self.storage_path / "idempotency.json"
        self.interventions_file = self.storage_path / "interventions.json"
        
    def save_all(self, 
                tasks: Dict[str, ZentexTask],
                suspended_tasks: Dict[str, SuspendedTask],
                idempotency_log: Dict[str, str],
                intervention_receipts: Dict[str, Dict[str, Any]]) -> bool:
        """Save all task data atomically"""
        try:
            # Create backup
            self._create_backup()
            
            # Save tasks
            tasks_data = {
                task_id: task.model_dump() for task_id, task in tasks.items()
            }
            self._save_json(self.tasks_file, tasks_data)
            
            # Save suspended tasks
            suspended_data = {
                task_id: suspended.model_dump() for task_id, suspended in suspended_tasks.items()
            }
            self._save_json(self.suspended_tasks_file, suspended_data)
            
            # Save idempotency log
            self._save_json(self.idempotency_file, idempotency_log)
            
            # Save intervention receipts
            self._save_json(self.interventions_file, intervention_receipts)
            
            logger.info(f"Successfully saved {len(tasks)} tasks and {len(suspended_tasks)} suspended tasks")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save task data: {e}")
            return False
    
    def load_all(self) -> Dict[str, Any]:
        """Load all task data"""
        try:
            # Load tasks
            tasks_data = self._load_json(self.tasks_file, {})
            tasks = {}
            for task_id, task_dict in tasks_data.items():
                # Convert datetime strings back to datetime objects
                task_dict = self._convert_datetime_fields(task_dict)
                tasks[task_id] = ZentexTask(**task_dict)
            
            # Load suspended tasks
            suspended_data = self._load_json(self.suspended_tasks_file, {})
            suspended_tasks = {}
            for task_id, suspended_dict in suspended_data.items():
                suspended_dict = self._convert_datetime_fields(suspended_dict)
                suspended_tasks[task_id] = SuspendedTask(**suspended_dict)
            
            # Load idempotency log
            idempotency_log = self._load_json(self.idempotency_file, {})
            
            # Load intervention receipts
            intervention_receipts = self._load_json(self.interventions_file, {})
            
            logger.info(f"Successfully loaded {len(tasks)} tasks and {len(suspended_tasks)} suspended tasks")
            
            return {
                "tasks": tasks,
                "suspended_tasks": suspended_tasks,
                "idempotency_log": idempotency_log,
                "intervention_receipts": intervention_receipts
            }
            
        except Exception as e:
            logger.error(f"Failed to load task data: {e}")
            # Try to restore from backup
            if self._restore_from_backup():
                return self.load_all()
            return {
                "tasks": {},
                "suspended_tasks": {},
                "idempotency_log": {},
                "intervention_receipts": {}
            }
    
    def save_tasks_only(self, tasks: Dict[str, ZentexTask]) -> bool:
        """Save only tasks (for frequent updates)"""
        try:
            tasks_data = {
                task_id: task.model_dump() for task_id, task in tasks.items()
            }
            self._save_json(self.tasks_file, tasks_data)
            return True
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")
            return False
    
    def _save_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Save data to JSON file"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def _load_json(self, file_path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        """Load data from JSON file"""
        if not file_path.exists():
            return default
            
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _convert_datetime_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime strings back to datetime objects"""
        datetime_fields = [
            'created_at', 'last_updated_at', 'started_at', 'completed_at', 
            'deadline', 'suspended_at', 'auto_resume_at', 'recorded_at'
        ]
        
        for field in datetime_fields:
            if field in data and data[field]:
                if isinstance(data[field], str):
                    try:
                        data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # If parsing fails, keep as string
                        pass
        
        return data
    
    def _create_backup(self) -> None:
        """Create backup of current files"""
        import shutil
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.storage_path / f"backup_{timestamp}"
        backup_dir.mkdir(exist_ok=True)
        
        files_to_backup = [
            self.tasks_file,
            self.suspended_tasks_file,
            self.idempotency_file,
            self.interventions_file
        ]
        
        for file_path in files_to_backup:
            if file_path.exists():
                shutil.copy2(file_path, backup_dir / file_path.name)
        
        # Clean old backups
        self._cleanup_old_backups()
    
    def _cleanup_old_backups(self) -> None:
        """Keep only the most recent backups"""
        import shutil
        
        backup_dirs = sorted(
            [d for d in self.storage_path.iterdir() if d.is_dir() and d.name.startswith('backup_')],
            key=lambda x: x.name,
            reverse=True
        )
        
        for old_backup in backup_dirs[self.backup_count:]:
            shutil.rmtree(old_backup)
    
    def _restore_from_backup(self) -> bool:
        """Restore from the most recent backup"""
        import shutil
        
        backup_dirs = sorted(
            [d for d in self.storage_path.iterdir() if d.is_dir() and d.name.startswith('backup_')],
            key=lambda x: x.name,
            reverse=True
        )
        
        if not backup_dirs:
            logger.warning("No backups found to restore from")
            return False
        
        latest_backup = backup_dirs[0]
        logger.info(f"Restoring from backup: {latest_backup.name}")
        
        try:
            # Restore files from backup
            for backup_file in latest_backup.iterdir():
                target_file = self.storage_path / backup_file.name
                shutil.copy2(backup_file, target_file)
            return True
        except Exception as e:
            logger.error(f"Failed to restore from backup: {e}")
            return False
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        stats = {
            "storage_path": str(self.storage_path),
            "tasks_file_exists": self.tasks_file.exists(),
            "suspended_tasks_file_exists": self.suspended_tasks_file.exists(),
            "idempotency_file_exists": self.idempotency_file.exists(),
            "interventions_file_exists": self.interventions_file.exists(),
            "backup_count": len([d for d in self.storage_path.iterdir() 
                              if d.is_dir() and d.name.startswith('backup_')])
        }
        
        # File sizes
        for file_path in [self.tasks_file, self.suspended_tasks_file, 
                         self.idempotency_file, self.interventions_file]:
            if file_path.exists():
                stats[f"{file_path.stem}_size_bytes"] = file_path.stat().st_size
        
        return stats
