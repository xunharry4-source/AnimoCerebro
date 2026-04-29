from __future__ import annotations
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
    db = DatabaseConnection(get_storage_paths().core_db)
    cache = LRUCache(max_size=1000, ttl_seconds=60)
    dao = TaskDAO(db, cache)

    # Create task
    dao.create_task(task_data)

    # Query tasks
    tasks = dao.list_tasks(status="in_progress")
"""


import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zentex.common.database import BaseDAO, DatabaseConnection, LRUCache
from zentex.tasks.schema import ensure_task_database_schema

logger = logging.getLogger(__name__)


class TaskDAO(BaseDAO):
    """Data Access Object for Task entities."""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        ensure_task_database_schema(db)
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
            raise
    
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
            raise
    
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
        target_id: Optional[str] = None,
        source_module: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        overdue_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters applied in SQLite."""
        where_clause, params = self._build_task_filter_clause(
            status=status,
            priority=priority,
            task_type=task_type,
            parent_task_id=parent_task_id,
            originator_id=originator_id,
            target_id=target_id,
            source_module=source_module,
            metadata_filters=metadata_filters,
            tags=tags,
            overdue_only=overdue_only,
        )

        # Build query with ordering
        order_by = (
            "CASE priority "
            "WHEN 'critical' THEN 4 "
            "WHEN 'high' THEN 3 "
            "WHEN 'medium' THEN 2 "
            "WHEN 'low' THEN 1 "
            "ELSE 2 END DESC, created_at DESC"
        )
        query = f"SELECT * FROM tasks WHERE {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?"
        params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
        
        tasks = self.db.execute_query(query, tuple(params))
        return [self._deserialize_task(t) for t in tasks]

    def count_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        task_type: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        originator_id: Optional[str] = None,
        target_id: Optional[str] = None,
        source_module: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        overdue_only: bool = False,
    ) -> int:
        """Count tasks with the same database-backed filters used by list_tasks."""
        where_clause, params = self._build_task_filter_clause(
            status=status,
            priority=priority,
            task_type=task_type,
            parent_task_id=parent_task_id,
            originator_id=originator_id,
            target_id=target_id,
            source_module=source_module,
            metadata_filters=metadata_filters,
            tags=tags,
            overdue_only=overdue_only,
        )
        rows = self.db.execute_query(f"SELECT COUNT(*) AS count FROM tasks WHERE {where_clause}", tuple(params))
        return int(rows[0]["count"]) if rows else 0

    def _build_task_filter_clause(
        self,
        *,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        task_type: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        originator_id: Optional[str] = None,
        target_id: Optional[str] = None,
        source_module: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        overdue_only: bool = False,
    ) -> tuple[str, list[Any]]:
        conditions = []
        params: list[Any] = []

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
        if target_id:
            conditions.append("target_id = ?")
            params.append(target_id)
        if source_module:
            conditions.append("json_extract(metadata, '$.source_module') = ?")
            params.append(source_module)
        if metadata_filters:
            for key, value in metadata_filters.items():
                conditions.append("json_extract(metadata, ?) = ?")
                params.extend([f"$.{key}", value])
        if tags:
            placeholders = ", ".join("?" for _ in tags)
            conditions.append(
                f"EXISTS (SELECT 1 FROM json_each(tasks.tags) WHERE json_each.value IN ({placeholders}))"
            )
            params.extend(tags)
        if overdue_only:
            conditions.append("deadline < datetime('now') AND status NOT IN ('done', 'failed', 'archived')")

        return " AND ".join(conditions) if conditions else "1=1", params

    def list_tasks_depending_on(
        self,
        dependency_task_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List tasks whose depends_on JSON array contains dependency_task_id."""
        query = (
            "SELECT * FROM tasks "
            "WHERE EXISTS ("
            "SELECT 1 FROM json_each(tasks.depends_on) "
            "WHERE json_each.value = ?"
            ") "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        params = (
            dependency_task_id,
            max(1, min(int(limit), 500)),
            max(0, int(offset)),
        )
        tasks = self.db.execute_query(query, params)
        return [self._deserialize_task(t) for t in tasks]
    
    def get_subtasks(self, parent_task_id: str) -> List[Dict[str, Any]]:
        """Get all subtasks for a parent task."""
        tasks = self.find_by_condition("parent_task_id = ?", (parent_task_id,))
        return [self._deserialize_task(t) for t in tasks]
    
    def get_dependent_tasks(self, task_id: str) -> List[Dict[str, Any]]:
        """Get tasks that depend on the given task."""
        return self.list_tasks_depending_on(task_id)
    
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
                if isinstance(task[field], list):
                    continue
                try:
                    task[field] = json.loads(task[field])
                except (json.JSONDecodeError, TypeError):
                    task[field] = []
        
        for field in ['contract', 'metadata']:
            if field in task and task[field]:
                if isinstance(task[field], dict):
                    continue
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
            raise
    
    def resume_task(self, task_id: str) -> bool:
        """Resume a suspended task."""
        affected = self.db.execute_update(
            "DELETE FROM suspended_tasks WHERE task_id = ?",
            (task_id,),
        )
        success = affected > 0
        if success:
            self._invalidate_cache(f"{self.table_name}:")
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
    
    def list_suspended_tasks(
        self,
        *,
        task_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List suspended tasks with database-backed filtering and pagination."""
        capped_limit = max(1, min(int(limit), 500))
        normalized_offset = max(0, int(offset))
        if task_id:
            suspensions = self.find_by_condition(
                "task_id = ?",
                (task_id,),
                limit=capped_limit,
                offset=normalized_offset,
            )
        else:
            suspensions = self.find_all(limit=capped_limit, offset=normalized_offset)
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

    def count_suspended_tasks(self) -> int:
        """Count suspended tasks in the database without loading rows."""
        row = self.db.execute_query("SELECT COUNT(*) AS count FROM suspended_tasks")
        if not row:
            return 0
        first = row[0]
        if isinstance(first, dict):
            return int(first.get("count") or 0)
        return int(first["count"])

    def get_auto_resume_tasks(self, *, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get tasks ready for auto-resume with pagination."""
        query = (
            "SELECT * FROM suspended_tasks "
            "WHERE auto_resume_at IS NOT NULL AND auto_resume_at <= datetime('now') "
            "ORDER BY auto_resume_at ASC LIMIT ? OFFSET ?"
        )
        results = self.db.execute_query(query, (max(1, min(int(limit), 500)), max(0, int(offset))))
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
            raise
    
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


class TaskOutcomeDAO(BaseDAO):
    """Data Access Object for task outcome binding records."""

    JSON_FIELDS = {
        "objective_profile",
        "evaluation_profile",
        "expected_outcome",
        "success_criteria",
        "acceptance_conditions",
        "risk_assessment",
        "actual_outcome",
        "deviation_report",
        "verification_result",
        "user_feedback",
    }

    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self.table_name = "task_outcomes"

    def _get_id_column(self) -> str:
        return "task_id"

    def upsert_outcome(self, outcome_data: Dict[str, Any]) -> bool:
        if not outcome_data.get("task_id"):
            raise ValueError("task_outcomes requires task_id")

        if not outcome_data.get("created_at"):
            outcome_data = {
                **outcome_data,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        processed: Dict[str, Any] = {}
        for key, value in outcome_data.items():
            if key in self.JSON_FIELDS and value is not None:
                processed[key] = json.dumps(value, ensure_ascii=False, default=str)
            elif key == "overall_passed" and isinstance(value, bool):
                processed[key] = 1 if value else 0
            else:
                processed[key] = value

        columns = list(processed.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        update_sql = ", ".join(
            f"{column}=excluded.{column}"
            for column in columns
            if column not in {"task_id", "created_at"}
        )
        query = (
            f"INSERT INTO {self.table_name} ({column_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT(task_id) DO UPDATE SET {update_sql}"
        )
        affected = self.db.execute_update(query, tuple(processed[column] for column in columns))
        self._invalidate_cache(f"{self.table_name}:")
        return affected > 0

    def get_outcome(self, task_id: str) -> Optional[Dict[str, Any]]:
        row = self.find_by_id(task_id)
        if not row:
            return None
        return self._deserialize_outcome(row)

    def mark_reflection_written(self, task_id: str, reflection_id: str) -> bool:
        if not task_id:
            raise ValueError("task_outcomes reflection writeback requires task_id")
        if not reflection_id:
            raise ValueError("task_outcomes reflection writeback requires reflection_id")
        affected = self.db.execute_update(
            f"""
            UPDATE {self.table_name}
            SET written_back_to_reflection = 1,
                reflection_id = ?
            WHERE task_id = ?
            """,
            (reflection_id, task_id),
        )
        self._invalidate_cache(f"{self.table_name}:")
        return affected > 0

    def mark_memory_written(self, task_id: str, memory_id: str) -> bool:
        if not task_id:
            raise ValueError("task_outcomes memory writeback requires task_id")
        if not memory_id:
            raise ValueError("task_outcomes memory writeback requires memory_id")
        affected = self.db.execute_update(
            f"""
            UPDATE {self.table_name}
            SET written_back_to_memory = 1,
                memory_id = ?
            WHERE task_id = ?
            """,
            (memory_id, task_id),
        )
        self._invalidate_cache(f"{self.table_name}:")
        return affected > 0

    def mark_learning_written(self, task_id: str, learning_trace_id: str) -> bool:
        if not task_id:
            raise ValueError("task_outcomes learning writeback requires task_id")
        if not learning_trace_id:
            raise ValueError("task_outcomes learning writeback requires learning_trace_id")
        affected = self.db.execute_update(
            f"""
            UPDATE {self.table_name}
            SET written_back_to_learning = 1,
                learning_trace_id = ?
            WHERE task_id = ?
            """,
            (learning_trace_id, task_id),
        )
        self._invalidate_cache(f"{self.table_name}:")
        return affected > 0

    def _deserialize_outcome(self, row: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(row)
        for field in self.JSON_FIELDS:
            if field in data and isinstance(data[field], str) and data[field]:
                try:
                    data[field] = json.loads(data[field])
                except (json.JSONDecodeError, TypeError):
                    data[field] = None
        if data.get("overall_passed") is not None:
            data["overall_passed"] = bool(data["overall_passed"])
        for field in ("written_back_to_reflection", "written_back_to_learning", "written_back_to_memory"):
            if data.get(field) is not None:
                data[field] = bool(data[field])
        return data


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
