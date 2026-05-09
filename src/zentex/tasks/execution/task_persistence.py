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


def _non_empty_text(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _stable_suffix(value: Any, fallback: str) -> str:
    text = str(value or fallback or "").strip().lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in text)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:64] or fallback


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _external_executor_metadata(task_data: dict[str, Any], metadata: dict[str, Any], target_id: str, executor_type: str) -> dict[str, Any]:
    if executor_type == "connector":
        executor_type = "external_connector"
    capabilities = _string_list(task_data.get("required_capabilities")) or _string_list(metadata.get("required_capabilities"))
    out: dict[str, Any] = {"external_executor_type": executor_type}
    if executor_type == "cli":
        tool = str(
            task_data.get("cli_tool_name")
            or metadata.get("cli_tool_name")
            or metadata.get("tool_name")
            or (target_id.removeprefix("cli:") if target_id.startswith("cli:") else "")
        ).strip()
        out["cli_tool_name"] = tool
        capabilities += ["external.cli"] + ([f"cli.{tool}"] if tool else [])
    elif executor_type == "mcp":
        server = str(metadata.get("mcp_server_id") or task_data.get("mcp_server_id") or "").strip()
        tool = str(metadata.get("mcp_tool_name") or task_data.get("mcp_tool_name") or "").strip()
        if target_id.startswith("mcp:"):
            parts = target_id.split(":", 2)
            server = server or (parts[1] if len(parts) >= 2 else "")
            tool = tool or (parts[2] if len(parts) == 3 else "")
        out.update({"mcp_server_id": server, "mcp_tool_name": tool})
        capabilities += ["external.mcp"] + ([f"mcp.{server}.{tool}"] if server and tool else [])
    elif executor_type == "external_connector":
        connector = str(
            metadata.get("external_connector_id")
            or task_data.get("external_connector_id")
            or metadata.get("connector_id")
            or (target_id.removeprefix("external_connector:") if target_id.startswith("external_connector:") else "")
        ).strip()
        capability = str(
            metadata.get("external_connector_capability")
            or task_data.get("external_connector_capability")
            or metadata.get("connector_capability")
            or metadata.get("capability")
            or ""
        ).strip()
        out.update({"external_connector_id": connector, "external_connector_capability": capability})
        capabilities += ["external.external_connector"] + (
            [f"external_connector.{connector}.{capability}"] if connector and capability else []
        )
    elif executor_type == "agent":
        agent_id = str(
            metadata.get("agent_id")
            or task_data.get("agent_id")
            or (target_id.removeprefix("agent:") if target_id.startswith("agent:") else "")
        ).strip()
        out["agent_id"] = agent_id
        capabilities += ["external.agent"] + ([f"agent.{agent_id}"] if agent_id else [])
    out["required_capabilities"] = list(dict.fromkeys(capabilities))
    return out

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
        task_id = task_data.get("task_id") or task_data.get("id") or f"task_{uuid4().hex[:8]}"
        metadata = task_data.get("metadata") if isinstance(task_data.get("metadata"), dict) else {}
        task_scope = self._derive_task_scope(task_data)
        executor_type = str(task_data.get("executor_type") or metadata.get("executor_type") or "").strip()
        if task_scope == "internal":
            executor_type = "internal"
        target_id = str(task_data.get("target_id") or metadata.get("target_id") or "").strip()
        if task_scope == "internal":
            target_id = target_id or "internal:task_constraint_checker"
        worker_dispatch_enabled = bool(task_scope == "external" and target_id)
        if task_scope == "internal":
            worker_dispatch_enabled = True
        required_capabilities = _string_list(task_data.get("required_capabilities")) or _string_list(metadata.get("required_capabilities"))
        internal_executor_plugin_id = ""
        if task_scope == "internal" and not required_capabilities:
            required_capabilities = ["task.constraint_checking"]
        if task_scope == "internal":
            internal_executor_plugin_id = str(
                metadata.get("internal_executor_plugin_id")
                or metadata.get("executor_id")
                or (target_id.removeprefix("internal:") if target_id.startswith("internal:") else "")
                or "task_constraint_checker"
            ).strip()
            if internal_executor_plugin_id not in required_capabilities:
                required_capabilities.append(internal_executor_plugin_id)
        external_executor = (
            _external_executor_metadata(task_data, metadata, target_id, executor_type)
            if task_scope == "external"
            else {}
        )
        if task_scope == "external":
            required_capabilities = list(external_executor.get("required_capabilities") or required_capabilities)
        stable_task_id = _stable_suffix(task_id, "task")
        idempotency_key = f"q8-plan-{session_id}-{queue_name}-{stable_task_id}"
        title = _non_empty_text(
            task_data.get("title"),
            f"Q8 {queue_name} task: {stable_task_id}",
        )
        reason = str(task_data.get("reason") or task_data.get("description") or "").strip()
        generation_basis = {
            "data_sources": ["q8_objective", "q8_task_queue"],
            "generation_functions": ["TaskPersistenceService.persist_plan", "TaskPersistenceService._write_db_task_record"],
            "plugin_references": [value for value in [internal_executor_plugin_id or target_id] if value],
            "source_task_id": str(task_data.get("task_id") or task_data.get("id") or "").strip(),
        }
        remarks_parts = [f"Q8 queue: {queue_name}", f"Executor: {target_id or 'pending-assignment'}"]
        remarks_parts.append("Generation data: " + ", ".join(generation_basis["data_sources"]))
        remarks_parts.append("Generation functions: " + ", ".join(generation_basis["generation_functions"]))
        if generation_basis["plugin_references"]:
            remarks_parts.append("Generation plugins/executors: " + ", ".join(generation_basis["plugin_references"]))
        if reason:
            remarks_parts.append(f"Reason: {reason}")
        if required_capabilities:
            remarks_parts.append("Executor capabilities: " + ", ".join(required_capabilities[:6]))
        standard_task = {
            "task_id": task_id,
            "idempotency_key": idempotency_key,
            "title": title,
            "task_type": "cognitive_step",
            "task_scope": task_scope,
            "status": status,
            "priority": _non_empty_text(task_data.get("priority"), "medium"),
            "originator_id": f"q8_planning_session_{session_id}",
            "target_id": target_id or None,
            "remarks": "\n".join(remarks_parts),
            "metadata": {
                "source": "nine_questions.q8",
                "session_id": session_id,
                "turn_id": turn_id,
                "queue_name": queue_name,
                "q8_generated_task_id": str(task_data.get("task_id") or task_data.get("id") or "").strip(),
                "q8_generated_task_uid": idempotency_key,
                "source_module": "nine_questions.q8",
                "source_chain": metadata.get("source_chain") or ("external_q8" if task_scope == "external" else "internal_q8"),
                "task_scope": task_scope,
                "executor_type": executor_type,
                "executor_id": internal_executor_plugin_id if task_scope == "internal" else target_id,
                "internal_executor_plugin_id": internal_executor_plugin_id,
                "target_id": target_id,
                "worker_dispatch_enabled": worker_dispatch_enabled,
                "required_capabilities": required_capabilities,
                "generation_basis": generation_basis,
                **external_executor,
                "tool_id": task_data.get("tool_id"),
                "raw_payload": task_data
            },
            "created_at": timestamp,
            "last_updated_at": timestamp
        }
        existing = self._task_dao.list_tasks(
            source_module="nine_questions.q8",
            metadata_filters={"q8_generated_task_uid": idempotency_key},
            limit=1,
            offset=0,
        )
        if existing:
            existing_task_id = str(existing[0]["task_id"])
            update_payload = {
                key: value
                for key, value in standard_task.items()
                if key not in {"task_id", "created_at"}
            }
            if not self._task_dao.update_task(existing_task_id, update_payload):
                raise RuntimeError(f"Task DAO rejected Q8 task update: {existing_task_id}")
            return
        task_id_collision = self._task_dao.get_task(str(standard_task["task_id"]))
        if task_id_collision is not None:
            standard_task["task_id"] = _stable_suffix(idempotency_key, f"q8-{stable_task_id}")
            standard_task["metadata"]["physical_task_id_collision"] = {
                "raw_task_id": str(task_id),
                "resolved_task_id": standard_task["task_id"],
                "reason": "q8_generated_task_id_is_not_globally_unique",
            }
        if not self._task_dao.create_task(standard_task):
            raise RuntimeError(f"Task DAO rejected Q8 task persistence: {task_id}")

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
