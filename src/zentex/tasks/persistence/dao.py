"""
Task Data Access Object for persistent storage.

This module provides database operations for Task management, including
task CRUD, dependency tracking, suspension, and audit logging.

Responsibilities:
- CRUD operations for tasks table
- Subtask hierarchy management
- Suspension/resume operations
- Audit trail maintenance
- Statistical queries

Architecture:
- Extends BaseDAO for common operations
- Handles JSON serialization for complex fields
- Integrates with LRUCache for performance

Usage:
    db = DatabaseConnection("runtime/data/zentex_core.db")
    cache = LRUCache(max_size=1000, ttl_seconds=60)
    dao = TaskDAO(db, cache)
    
    # Create task
    dao.create_task(task_data)
    
    # Query tasks
    tasks = dao.list_tasks(status="in_progress")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zentex.common.database import BaseDAO, DatabaseConnection, LRUCache

logger = logging.getLogger(__name__)


class TaskDAO(BaseDAO):
    """Data Access Object for Task entities."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "tasks"
    
    def _get_id_column(self) -> str:
        """Override to use task_id as primary key."""
        return "task_id"
    
    def create_task(self, task_data: Dict[str, Any]) -> bool:
        """Create a new task."""
        try:
            # Serialize JSON fields
            if 'subtask_ids' in task_data and isinstance(task_data['subtask_ids'], list):
                task_data['subtask_ids'] = json.dumps(task_data['subtask_ids'])
            if 'depends_on' in task_data and isinstance(task_data['depends_on'], list):
                task_data['depends_on'] = json.dumps(task_data['depends_on'])
            if 'tags' in task_data and isinstance(task_data['tags'], list):
                task_data['tags'] = json.dumps(task_data['tags'])
            if 'contract' in task_data and isinstance(task_data['contract'], dict):
                task_data['contract'] = json.dumps(task_data['contract'])
            if 'metadata' in task_data and isinstance(task_data['metadata'], dict):
                task_data['metadata'] = json.dumps(task_data['metadata'])
            
            success = self.insert(task_data)
            if success:
                logger.info(f"Task created: {task_data['task_id']}")
            return success
        except Exception as e:
            logger.error(f"Failed to create task: {e}", exc_info=True)
            return False
    
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing task."""
        try:
            # Serialize JSON fields if present
            if 'subtask_ids' in updates and isinstance(updates['subtask_ids'], list):
                updates['subtask_ids'] = json.dumps(updates['subtask_ids'])
            if 'depends_on' in updates and isinstance(updates['depends_on'], list):
                updates['depends_on'] = json.dumps(updates['depends_on'])
            if 'tags' in updates and isinstance(updates['tags'], list):
                updates['tags'] = json.dumps(updates['tags'])
            if 'contract' in updates and isinstance(updates['contract'], dict):
                updates['contract'] = json.dumps(updates['contract'])
            if 'metadata' in updates and isinstance(updates['metadata'], dict):
                updates['metadata'] = json.dumps(updates['metadata'])
            
            # Auto-update last_updated_at
            updates['last_updated_at'] = datetime.now(timezone.utc).isoformat()
            
            success = self.update(task_id, updates)
            if success:
                logger.info(f"Task updated: {task_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to update task: {e}", exc_info=True)
            return False
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID."""
        task = self.find_by_id(task_id)
        if task:
            return self._deserialize_task(task)
        return None
    
    def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        task_type: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        originator_id: Optional[str] = None,
        overdue_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters."""
        conditions = []
        params = []
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)
        if parent_task_id:
            conditions.append("parent_task_id = ?")
            params.append(parent_task_id)
        if originator_id:
            conditions.append("originator_id = ?")
            params.append(originator_id)
        if overdue_only:
            conditions.append("deadline < datetime('now') AND status NOT IN ('done', 'failed', 'archived')")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Build query with ordering
        order_by = "created_at DESC"
        query = f"SELECT * FROM tasks WHERE {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        tasks = self.db.execute_query(query, tuple(params))
        return [self._deserialize_task(t) for t in tasks]
    
    def get_subtasks(self, parent_task_id: str) -> List[Dict[str, Any]]:
        """Get all subtasks for a parent task."""
        tasks = self.find_by_condition("parent_task_id = ?", (parent_task_id,))
        return [self._deserialize_task(t) for t in tasks]
    
    def get_dependent_tasks(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all tasks that depend on the given task."""
        # This requires checking the depends_on JSON field
        all_tasks = self.find_all()
        dependent_tasks = []
        for task in all_tasks:
            deserialized = self._deserialize_task(task)
            if task_id in deserialized.get('depends_on', []):
                dependent_tasks.append(deserialized)
        return dependent_tasks
    
    def delete_task(self, task_id: str, force: bool = False) -> bool:
        """Delete a task (with safety checks)."""
        if not force:
            # Check for dependent tasks
            dependents = self.get_dependent_tasks(task_id)
            if dependents:
                logger.warning(f"Cannot delete task {task_id}: has {len(dependents)} dependent tasks")
                return False
            
            # Check status
            task = self.get_task(task_id)
            if task and task['status'] == 'in_progress':
                logger.warning(f"Cannot delete task {task_id}: task is in progress")
                return False
        
        return self.delete(task_id)
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get task statistics."""
        query = """
            SELECT 
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'todo' THEN 1 ELSE 0 END) as todo_count,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_count,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
                SUM(CASE WHEN status = 'suspended' THEN 1 ELSE 0 END) as suspended_count,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked_count,
                AVG(progress) as avg_progress
            FROM tasks
        """
        result = self.db.execute_query(query)
        if result:
            row = result[0]
            return {
                'total_tasks': row['total_tasks'],
                'todo_count': row['todo_count'],
                'in_progress_count': row['in_progress_count'],
                'done_count': row['done_count'],
                'failed_count': row['failed_count'],
                'suspended_count': row['suspended_count'],
                'blocked_count': row['blocked_count'],
                'avg_progress': row['avg_progress'] or 0.0
            }
        return {}
    
    def _deserialize_task(self, task_row: Any) -> Dict[str, Any]:
        """Deserialize JSON fields from database row."""
        if isinstance(task_row, dict):
            task = task_row.copy()
        else:
            task = dict(task_row)
        
        # Deserialize JSON fields
        for field in ['subtask_ids', 'depends_on', 'tags']:
            if field in task and task[field]:
                try:
                    task[field] = json.loads(task[field])
                except (json.JSONDecodeError, TypeError):
                    task[field] = []
        
        for field in ['contract', 'metadata']:
            if field in task and task[field]:
                try:
                    task[field] = json.loads(task[field])
                except (json.JSONDecodeError, TypeError):
                    task[field] = {}
        
        return task


class SuspendedTaskDAO(BaseDAO):
    """Data Access Object for Suspended Tasks."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "suspended_tasks"
    
    def _get_id_column(self) -> str:
        """Override to use task_id as unique identifier."""
        return "task_id"
    
    def suspend_task(self, suspension_data: Dict[str, Any]) -> bool:
        """Suspend a task."""
        try:
            # Serialize JSON fields
            if 'recovery_conditions' in suspension_data and isinstance(suspension_data['recovery_conditions'], list):
                suspension_data['recovery_conditions'] = json.dumps(suspension_data['recovery_conditions'])
            if 'suspension_context' in suspension_data and isinstance(suspension_data['suspension_context'], dict):
                suspension_data['suspension_context'] = json.dumps(suspension_data['suspension_context'])
            
            success = self.insert(suspension_data)
            if success:
                logger.info(f"Task suspended: {suspension_data['task_id']}")
            return success
        except Exception as e:
            logger.error(f"Failed to suspend task: {e}", exc_info=True)
            return False
    
    def resume_task(self, task_id: str) -> bool:
        """Resume a suspended task."""
        success = self.delete_by_condition("task_id = ?", (task_id,))
        if success:
            logger.info(f"Task resumed: {task_id}")
        return success
    
    def get_suspended_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get suspension info for a task."""
        results = self.find_by_condition("task_id = ?", (task_id,))
        if results:
            suspension = results[0]
            if isinstance(suspension, dict):
                data = suspension.copy()
            else:
                data = dict(suspension)
            
            # Deserialize JSON fields
            for field in ['recovery_conditions', 'suspension_context']:
                if field in data and data[field]:
                    try:
                        data[field] = json.loads(data[field])
                    except (json.JSONDecodeError, TypeError):
                        data[field] = [] if field == 'recovery_conditions' else {}
            
            return data
        return None
    
    def list_suspended_tasks(self) -> List[Dict[str, Any]]:
        """List all suspended tasks."""
        suspensions = self.find_all()
        result = []
        for s in suspensions:
            if isinstance(s, dict):
                data = s.copy()
            else:
                data = dict(s)
            
            # Deserialize JSON fields
            for field in ['recovery_conditions', 'suspension_context']:
                if field in data and data[field]:
                    try:
                        data[field] = json.loads(data[field])
                    except (json.JSONDecodeError, TypeError):
                        data[field] = [] if field == 'recovery_conditions' else {}
            
            result.append(data)
        return result
    
    def get_auto_resume_tasks(self) -> List[Dict[str, Any]]:
        """Get tasks ready for auto-resume."""
        query = "SELECT * FROM suspended_tasks WHERE auto_resume_at IS NOT NULL AND auto_resume_at <= datetime('now')"
        results = self.db.execute_query(query)
        return [dict(r) for r in results]


class TaskAuditLogDAO(BaseDAO):
    """Data Access Object for Task Audit Logs."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "task_audit_log"
    
    def log_action(
        self,
        task_id: str,
        action: str,
        operator_id: str = "system",
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ) -> bool:
        """Log a task action."""
        try:
            audit_data = {
                'task_id': task_id,
                'action': action,
                'operator_id': operator_id,
                'old_status': old_status,
                'new_status': new_status,
                'details': json.dumps(details) if details else None,
                'trace_id': trace_id
            }
            success = self.insert(audit_data)
            if success:
                logger.debug(f"Audit log created: {action} for task {task_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to log audit action: {e}", exc_info=True)
            return False
    
    def get_audit_history(
        self,
        task_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get audit history for a task."""
        logs = self.find_by_condition(
            "task_id = ?",
            (task_id,),
            order_by="timestamp DESC",
            limit=limit,
            offset=offset
        )
        
        result = []
        for log in logs:
            if isinstance(log, dict):
                data = log.copy()
            else:
                data = dict(log)
            
            if 'details' in data and data['details']:
                try:
                    data['details'] = json.loads(data['details'])
                except (json.JSONDecodeError, TypeError):
                    data['details'] = {}
            
            result.append(data)
        
        return result


class InterventionReceiptDAO(BaseDAO):
    """Data Access Object for Intervention Receipts."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "intervention_receipts"
    
    def _get_id_column(self) -> str:
        """Override to use idempotency_key as primary key."""
        return "idempotency_key"
    
    def record_intervention(self, receipt_data: Dict[str, Any]) -> bool:
        """Record an intervention receipt."""
        return self.insert(receipt_data)
    
    def get_receipt_by_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Get receipt by idempotency key."""
        results = self.find_by_condition("idempotency_key = ?", (idempotency_key,))
        return results[0] if results else None
    
    def get_interventions_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all interventions for a task."""
        return self.find_by_condition("task_id = ?", (task_id,))


class IdempotencyLogDAO(BaseDAO):
    """Data Access Object for Idempotency Log."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "idempotency_log"
    
    def _get_id_column(self) -> str:
        """Override to use idempotency_key as primary key."""
        return "idempotency_key"
    
    def check_idempotency(self, idempotency_key: str) -> Optional[str]:
        """Check if idempotency key exists, returns task_id if found."""
        results = self.find_by_condition("idempotency_key = ?", (idempotency_key,))
        return results[0]['task_id'] if results else None
    
    def record_idempotency(self, idempotency_key: str, task_id: str) -> bool:
        """Record an idempotency key."""
        return self.insert({
            'idempotency_key': idempotency_key,
            'task_id': task_id
        })
