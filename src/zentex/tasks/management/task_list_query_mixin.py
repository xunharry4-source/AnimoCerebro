from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceListQueryMixin:
    def list_tasks(self,
                 status: Optional[TaskStatus] = None,
                 priority: Optional[TaskPriority] = None,
                 tags: Optional[List[str]] = None,
                 parent_task_id: Optional[str] = None,
                 task_type: Optional[TaskType] = None,
                 task_scope: Optional[TaskScope] = None,
                 originator_id: Optional[str] = None,
                 target_id: Optional[str] = None,
                 overdue_only: bool = False,
                 source_module: Optional[str] = None,
                 metadata_filters: Optional[Dict[str, Any]] = None,
                 root_only: bool = False,
                 limit: int = 100,
                 offset: int = 0) -> List[ZentexTask]:
        """List tasks with database-backed filtering and pagination."""
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")
        capped_limit = max(1, min(int(limit), 500))
        normalized_offset = max(0, int(offset))
        db_tasks = self._task_dao.list_tasks(
            status=status.value if status else None,
            priority=priority.value if priority else None,
            task_type=task_type.value if task_type else None,
            task_scope=task_scope.value if task_scope else None,
            parent_task_id=parent_task_id,
            originator_id=originator_id,
            target_id=target_id,
            source_module=source_module,
            metadata_filters=metadata_filters,
            tags=tags,
            overdue_only=overdue_only,
            root_only=root_only,
            limit=capped_limit,
            offset=normalized_offset,
        )
        return [self._attach_validated_execution_assignment(self._dict_to_task(item)) for item in db_tasks]

    def count_tasks(self,
                    status: Optional[TaskStatus] = None,
                    priority: Optional[TaskPriority] = None,
                    tags: Optional[List[str]] = None,
                    parent_task_id: Optional[str] = None,
                    task_type: Optional[TaskType] = None,
                    task_scope: Optional[TaskScope] = None,
                    originator_id: Optional[str] = None,
                    target_id: Optional[str] = None,
                    overdue_only: bool = False,
                    source_module: Optional[str] = None,
                    metadata_filters: Optional[Dict[str, Any]] = None,
                    root_only: bool = False) -> int:
        """Count tasks using the same database-backed filters as list_tasks."""
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")
        return self._task_dao.count_tasks(
            status=status.value if status else None,
            priority=priority.value if priority else None,
            task_type=task_type.value if task_type else None,
            task_scope=task_scope.value if task_scope else None,
            parent_task_id=parent_task_id,
            originator_id=originator_id,
            target_id=target_id,
            source_module=source_module,
            metadata_filters=metadata_filters,
            tags=tags,
            overdue_only=overdue_only,
            root_only=root_only,
        )

    def list_tasks_page(
        self,
        *,
        presentation_group: str,
        source_module: Optional[str] = None,
        task_scope: Optional[TaskScope] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        root_only: bool = False,
        limit: int = 25,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return one database-backed page for a task-center presentation group."""
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")
        statuses = self._statuses_for_presentation_group(presentation_group)
        capped_limit = max(1, min(int(limit), 500))
        normalized_offset = max(0, int(offset))
        rows = self._task_dao.list_tasks(
            statuses=[status.value for status in statuses],
            source_module=source_module,
            task_scope=task_scope.value if task_scope else None,
            metadata_filters=metadata_filters,
            root_only=root_only,
            limit=capped_limit,
            offset=normalized_offset,
        )
        total = self._task_dao.count_tasks(
            statuses=[status.value for status in statuses],
            source_module=source_module,
            task_scope=task_scope.value if task_scope else None,
            metadata_filters=metadata_filters,
            root_only=root_only,
        )
        items = []
        for item in rows:
            task = self._attach_validated_execution_assignment(self._dict_to_task(item))
            payload = task.model_dump(mode="json")
            payload["subtask_count"] = len(task.subtask_ids)
            items.append(payload)
        return {
            "group": presentation_group,
            "items": items,
            "total": total,
            "limit": capped_limit,
            "offset": normalized_offset,
            "counts": self.count_tasks_by_presentation_group(
                source_module=source_module,
                task_scope=task_scope,
                metadata_filters=metadata_filters,
                root_only=root_only,
            ),
        }

    def count_tasks_by_presentation_group(
        self,
        *,
        source_module: Optional[str] = None,
        task_scope: Optional[TaskScope] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        root_only: bool = False,
    ) -> Dict[str, int]:
        """Return exact database counts for task-center presentation groups."""
        if not self._task_dao:
            raise RuntimeError("Task DAO is unavailable")
        return {
            group: self._task_dao.count_tasks(
                statuses=[status.value for status in self._statuses_for_presentation_group(group)],
                source_module=source_module,
                task_scope=task_scope.value if task_scope else None,
                metadata_filters=metadata_filters,
                root_only=root_only,
            )
            for group in (
                "all",
                "in_progress",
                "todo",
                "blocked",
                "pending",
                "waiting_confirmation",
                "completed",
                "failed",
                "suspended",
                "archived",
                "cancelled",
            )
        }


