import sqlite3
import logging
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.common.database import DatabaseConnection
from zentex.common.storage_paths import get_storage_paths
from zentex.tasks.persistence.dao import TaskDAO

logger = logging.getLogger(__name__)

class TaskPersistenceService:
    """
    Mandatory physical persistence for Q8 Decisions (Plans).
    
    Implements 'Option C':
    1. JSON Path: Writes atomic plan files to 'runtime_logs/tasks/' for physical evidence.
    2. SQLite Path: Writes tasks to a durable database for system execution.
    
    Policy: Eradicate 'Fake Planning'. If a plan cannot be persisted to BOTH 
    targets, the turn must halt to prevent unrecorded ghost actions.
    """

    def __init__(self, root_dir: Optional[Path] = None, db_path: Optional[str] = None):
        if root_dir is None:
            self.root_dir = Path(os.getcwd()) / "runtime_logs" / "tasks"
        else:
            self.root_dir = root_dir
            
        if db_path is None:
            self.db_path_str = str(get_storage_paths().core_db)
        else:
            self.db_path_str = str(db_path)
            
        self._ensure_infrastructure()

    def _ensure_infrastructure(self):
        """Initialize the TaskDAO and ensure physical directories exist."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize System DAO
        db = DatabaseConnection(self.db_path_str)
        self._task_dao = TaskDAO(db)
        logger.info(f"TaskPersistenceService: Connected to system DAO at {self.db_path_str}")

    def persist_plan(self, session_id: str, turn_id: str, objective: Dict[str, Any], task_queue: Dict[str, Any]):
        """
        Atomic dual-layer persistence of a Q8 decision.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        plan_id = f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{turn_id[:8]}"
        
        # 1. JSON Persistence (Physical Evidence)
        self._write_json_evidence(session_id, turn_id, plan_id, objective, task_queue, timestamp)
        
        # 2. SQLite Persistence (Execution Layer)
        self._write_db_records(session_id, turn_id, task_queue, timestamp)
        
        logger.info(f"PLAN PERSISTED: {plan_id} (JSON + SQLite)")

    def _write_json_evidence(self, session_id: str, turn_id: str, plan_id: str, objective: dict, task_queue: dict, timestamp: str):
        target_dir = self.root_dir / f"session_{session_id}" / f"turn_{turn_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = target_dir / "plan.json"
        payload = {
            "plan_id": plan_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "timestamp": timestamp,
            "objective": objective,
            "task_queue": task_queue
        }
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"INTEGRITY FAILURE: Plan JSON writing failed: {e}")
            raise RuntimeError(f"Audit log failure: Unwriteable task persistence path {file_path}")

    def _write_db_records(self, session_id: str, turn_id: str, task_queue: dict, timestamp: str):
        queue_specs = [
            ("next_self_tasks", "todo"),
            ("blocked_self_tasks", "blocked"),
            ("proactive_actions", "todo"),
        ]
        
        try:
            for queue_name, status in queue_specs:
                rows = task_queue.get(queue_name, [])
                if not isinstance(rows, list):
                    continue
                for task_data in rows:
                    if not isinstance(task_data, dict):
                        task_data = {"title": str(task_data)}
                    self._write_db_task_record(
                        session_id=session_id,
                        turn_id=turn_id,
                        queue_name=queue_name,
                        status=status,
                        task_data=task_data,
                        timestamp=timestamp,
                    )
        except Exception as e:
            logger.error(f"INTEGRITY FAILURE: Task DB insertion via DAO failed: {e}")
            raise RuntimeError(f"Database failure: Could not persist tasks for execution via system DAO.")

    def _write_db_task_record(
        self,
        *,
        session_id: str,
        turn_id: str,
        queue_name: str,
        status: str,
        task_data: dict[str, Any],
        timestamp: str,
    ) -> None:
        task_id = task_data.get("id") or f"task_{uuid4().hex[:8]}"
        metadata = task_data.get("metadata") if isinstance(task_data.get("metadata"), dict) else {}
        task_scope = self._derive_task_scope(task_data)
        executor_type = str(task_data.get("executor_type") or metadata.get("executor_type") or "").strip()
        if task_scope == "internal":
            executor_type = "internal"
        target_id = str(task_data.get("target_id") or metadata.get("target_id") or "").strip()
        standard_task = {
            "task_id": task_id,
            "idempotency_key": f"q8-plan-{session_id}-{turn_id}-{task_id}",
            "title": task_data.get("title", "Planned Task"),
            "task_type": "cognitive_step",
            "task_scope": task_scope,
            "status": status,
            "priority": task_data.get("priority", "medium"),
            "originator_id": f"q8_planning_session_{session_id}",
            "target_id": target_id or None,
            "remarks": task_data.get("description", ""),
            "metadata": {
                "session_id": session_id,
                "turn_id": turn_id,
                "queue_name": queue_name,
                "source_module": "q8_what_should_i_do_now",
                "source_chain": metadata.get("source_chain") or ("external_q8" if task_scope == "external" else "internal_q8"),
                "task_scope": task_scope,
                "executor_type": executor_type,
                "target_id": target_id,
                "tool_id": task_data.get("tool_id"),
                "raw_payload": task_data
            },
            "created_at": timestamp,
            "last_updated_at": timestamp
        }
        self._task_dao.create_task(standard_task)

    @staticmethod
    def _derive_task_scope(task_data: Dict[str, Any]) -> str:
        metadata = task_data.get("metadata") if isinstance(task_data.get("metadata"), dict) else {}
        explicit_scope = str(
            task_data.get("task_scope")
            or task_data.get("execution_scope")
            or task_data.get("scope")
            or metadata.get("task_scope")
            or ""
        ).strip().lower()
        if explicit_scope in {"internal", "external"}:
            return explicit_scope
        executor_type = str(task_data.get("executor_type") or metadata.get("executor_type") or "").strip().lower()
        target_id = str(task_data.get("target_id") or metadata.get("target_id") or "").strip().lower()
        if executor_type in {"agent", "cli", "mcp", "external_connector", "connector"}:
            return "external"
        if target_id.startswith(("agent:", "cli:", "mcp:", "external_connector:", "connector:")):
            return "external"
        return "internal"

# Global instance
task_persistence = TaskPersistenceService()
