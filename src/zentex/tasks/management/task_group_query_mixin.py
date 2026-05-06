from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceGroupQueryMixin:
    @staticmethod
    def _statuses_for_presentation_group(group: str) -> List[TaskStatus]:
        mapping = {
            "all": [
                TaskStatus.SPLIT_REQUIRED,
                TaskStatus.ASSIGNMENT_PENDING,
                TaskStatus.QUEUED,
                TaskStatus.TODO,
                TaskStatus.IN_PROGRESS,
                TaskStatus.BLOCKED,
                TaskStatus.WAITING_CONFIRMATION,
                TaskStatus.DONE,
                TaskStatus.FAILED,
                TaskStatus.SUSPENDED,
                TaskStatus.ARCHIVED,
                TaskStatus.CANCELLED,
            ],
            "in_progress": [TaskStatus.IN_PROGRESS],
            "todo": [TaskStatus.TODO, TaskStatus.QUEUED],
            "blocked": [TaskStatus.BLOCKED],
            "pending": [TaskStatus.SPLIT_REQUIRED, TaskStatus.ASSIGNMENT_PENDING, TaskStatus.TODO, TaskStatus.QUEUED, TaskStatus.BLOCKED],
            "waiting_confirmation": [TaskStatus.WAITING_CONFIRMATION],
            "completed": [TaskStatus.DONE],
            "failed": [TaskStatus.FAILED],
            "suspended": [TaskStatus.SUSPENDED],
            "archived": [TaskStatus.ARCHIVED],
            "cancelled": [TaskStatus.CANCELLED],
        }
        if group not in mapping:
            raise ValueError(f"Invalid task presentation group: {group}")
        return mapping[group]

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _task_noise_workspace_context(payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        return {
            "workspace_environment_context": metadata.get("workspace_environment_context")
            or metadata.get("environment_context")
            or metadata.get("q1_environment_snapshot")
            or {},
            "source_module": metadata.get("source_module") or metadata.get("source"),
            "target_id": payload.get("target_id"),
            "task_scope": payload.get("task_scope"),
            "task_type": payload.get("task_type"),
        }

    def list_tasks_grouped(
        self,
        *,
        source_module: Optional[str] = None,
        root_only: bool = False,
        limit_per_group: int = 100,
        offset: int = 0,
    ) -> Dict[str, List[ZentexTask]]:
        """Return tasks partitioned into presentation groups.

        Business rule: which statuses belong to each group is a domain
        decision and must not leak into web_console routers.
        """
        capped_limit = max(1, min(int(limit_per_group), 500))
        normalized_offset = max(0, int(offset))
        return {
            "in_progress": self.list_tasks(
                status=TaskStatus.IN_PROGRESS,
                source_module=source_module,
                root_only=root_only,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "todo": self.list_tasks(
                status=TaskStatus.TODO,
                source_module=source_module,
                root_only=root_only,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "blocked": self.list_tasks(
                status=TaskStatus.BLOCKED,
                source_module=source_module,
                root_only=root_only,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "pending": (
                self.list_tasks(
                    status=TaskStatus.TODO,
                    source_module=source_module,
                    root_only=root_only,
                    limit=capped_limit,
                    offset=normalized_offset,
                )
                + self.list_tasks(
                    status=TaskStatus.BLOCKED,
                    source_module=source_module,
                    root_only=root_only,
                    limit=capped_limit,
                    offset=normalized_offset,
                )
            )[:capped_limit],
            "waiting_confirmation": self.list_tasks(
                status=TaskStatus.WAITING_CONFIRMATION,
                source_module=source_module,
                root_only=root_only,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "completed": self.list_tasks(
                status=TaskStatus.DONE,
                source_module=source_module,
                root_only=root_only,
                limit=capped_limit,
                offset=normalized_offset,
            ),
            "cancelled": self.list_tasks(
                status=TaskStatus.CANCELLED,
                source_module=source_module,
                root_only=root_only,
                limit=capped_limit,
                offset=normalized_offset,
            ),
        }

