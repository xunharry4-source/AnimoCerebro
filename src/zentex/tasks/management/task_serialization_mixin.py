from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceSerializationMixin:
    @staticmethod
    def _derive_execution_assignment(data: Dict[str, Any]) -> Dict[str, Any]:
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        target_id = str(data.get("target_id") or "").strip()
        dispatch_plugin_id = str(data.get("dispatch_plugin_id") or "").strip()
        executor_type = str(metadata.get("executor_type") or "").strip()

        if target_id:
            assignment_type = executor_type or target_id.split(":", 1)[0]
            return {
                "status": "assigned",
                "source": "target_id",
                "executor_id": target_id,
                "executor_type": assignment_type,
                "label": target_id,
            }
        if dispatch_plugin_id:
            return {
                "status": "routed",
                "source": "dispatch_plugin_id",
                "executor_id": dispatch_plugin_id,
                "executor_type": "internal_plugin",
                "label": dispatch_plugin_id,
            }
        if executor_type:
            if executor_type == "mcp":
                server_id = str(metadata.get("mcp_server_id") or "").strip()
                tool_name = str(metadata.get("mcp_tool_name") or "").strip()
                executor_id = ":".join(part for part in ("mcp", server_id, tool_name) if part)
            elif executor_type == "cli":
                tool_name = str(metadata.get("cli_tool_name") or metadata.get("tool_name") or "").strip()
                executor_id = ":".join(part for part in ("cli", tool_name) if part)
            elif executor_type == "agent":
                executor_id = str(metadata.get("agent_id") or "").strip()
            else:
                executor_id = str(metadata.get("executor_id") or "").strip()
            return {
                "status": "declared",
                "source": "metadata",
                "executor_id": executor_id or executor_type,
                "executor_type": executor_type,
                "label": executor_id or executor_type,
            }
        status = data.get("status")
        status_value = getattr(status, "value", status)
        if status_value in {"todo", "queued"}:
            assignment_status = "pending_dispatch"
        elif status_value == "assignment_pending":
            assignment_status = "assignment_pending"
        elif status_value == "split_required":
            assignment_status = "split_required"
        elif status_value == "blocked":
            assignment_status = "dispatch_blocked"
        else:
            assignment_status = "unassigned"
        return {
            "status": assignment_status,
            "source": "none",
            "executor_id": "",
            "executor_type": "",
            "label": "",
        }

    @staticmethod
    def _derive_task_scope(data: Dict[str, Any]) -> str:
        raw_scope = data.get("task_scope") or data.get("execution_scope") or data.get("scope") or ""
        raw_scope = getattr(raw_scope, "value", raw_scope)
        explicit_scope = str(
            raw_scope
        ).strip().lower()
        if explicit_scope in {TaskScope.INTERNAL.value, TaskScope.EXTERNAL.value}:
            return explicit_scope

        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        executor_type = str(metadata.get("executor_type") or data.get("executor_type") or "").strip().lower()
        target_id = str(data.get("target_id") or "").strip().lower()
        task_type = data.get("task_type")
        task_type_value = str(getattr(task_type, "value", task_type) or "").strip().lower()

        external_executor_types = {"agent", "cli", "mcp", "external_connector", "connector"}
        external_target_prefixes = ("agent:", "cli:", "mcp:", "external_connector:", "connector:")
        if (
            task_type_value == TaskType.AGENT_DELEGATION.value
            or executor_type in external_executor_types
            or target_id.startswith(external_target_prefixes)
        ):
            return TaskScope.EXTERNAL.value
        return TaskScope.INTERNAL.value

    def _task_to_dict(self, task: ZentexTask) -> Dict[str, Any]:
        """Convert ZentexTask to dictionary for database storage."""
        return {
            'task_id': task.task_id,
            'parent_task_id': task.parent_task_id,
            'subtask_ids': task.subtask_ids,
            'depends_on': task.depends_on,
            'bundle_id': task.bundle_id,
            'subtask_id': task.subtask_id,
            'idempotency_key': task.idempotency_key,
            'title': task.title,
            'task_type': task.task_type.value,
            'task_scope': task.task_scope.value,
            'status': task.status.value,
            'priority': task.priority.value,
            'progress': task.progress,
            'originator_id': task.originator_id,
            'target_id': task.target_id,
            'remarks': task.remarks,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'estimated_duration': task.estimated_duration,
            'tags': task.tags,
            'contract': task.contract.model_dump() if hasattr(task.contract, 'model_dump') else dict(task.contract.__dict__),
            'metadata': task.metadata,
            'last_updated_at': task.last_updated_at.isoformat(),
            'created_at': task.created_at.isoformat(),
            'attempt_count': task.attempt_count,
            'last_error': task.last_error,
            'execution_started_at': task.execution_started_at,
            'execution_finished_at': task.execution_finished_at,
            'dispatch_plugin_id': task.dispatch_plugin_id,
            'execution_output': task.execution_output,
        }

    def _dict_to_task(self, data: Dict[str, Any]) -> ZentexTask:
        """Convert database dictionary to ZentexTask."""
        # Convert string enums back to enum types
        if 'task_type' in data and isinstance(data['task_type'], str):
            data['task_type'] = TaskType(data['task_type'])
        data['task_scope'] = TaskScope(self._derive_task_scope(data))
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = TaskStatus(data['status'])
        if 'priority' in data and isinstance(data['priority'], str):
            data['priority'] = TaskPriority(data['priority'])
        
        # Convert ISO format strings back to datetime
        for field in ['started_at', 'completed_at', 'deadline', 'last_updated_at', 'created_at']:
            if field in data and data[field] and isinstance(data[field], str):
                try:
                    data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    data[field] = None
        
        # Ensure collection fields are never None (Pydantic v2 requirement)
        # This prevents ValidationErrors when database columns contain NULL for these fields.
        for list_field in ['subtask_ids', 'depends_on', 'tags']:
            if data.get(list_field) is None:
                data[list_field] = []
        
        # Handle contract and metadata
        if data.get('contract') is None:
            data['contract'] = {}
        if data.get('metadata') is None:
            data['metadata'] = {}

        if 'contract' in data and isinstance(data['contract'], dict):
            data['contract'] = TaskContract(**data['contract'])

        data["execution_assignment"] = self._derive_execution_assignment(data)
        
        return ZentexTask(**data)

    def _sync_task_to_database(self, task: ZentexTask) -> bool:
        """Sync a task to database if database is enabled."""
        if not self.use_database or not self._task_dao:
            return False
        
        try:
            task_data = self._task_to_dict(task)
            return self._task_dao.create_task(task_data) if not self._task_dao.get_task(task.task_id) else self._task_dao.update_task(task.task_id, task_data)
        except Exception as e:
            logger.error(f"Failed to sync task to database: {e}")
            return False

    def _load_task_from_database(self, task_id: str) -> Optional[ZentexTask]:
        """Load a task from database if database is enabled."""
        if not self.use_database or not self._task_dao:
            return None
        
        try:
            data = self._task_dao.get_task(task_id)
            if data:
                return self._dict_to_task(data)
        except Exception as e:
            logger.error(f"Failed to load task from database: {e}")
        return None

