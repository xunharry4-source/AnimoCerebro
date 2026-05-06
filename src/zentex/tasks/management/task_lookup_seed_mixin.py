from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceLookupSeedMixin:
    def revision(self) -> int:
        """Monotonically increasing counter; 0 when the service has no tracker.

        Callers (e.g. WebSocket stream) use this to detect in-flight changes
        without accessing private attributes.
        """
        return getattr(self, "_revision", 0)

    def get_task(self, task_id: str) -> Optional[ZentexTask]:
        """Get a task by ID.
        
        G15: Truth Consolidation.
        Priority: Database (if enabled) > Shared Memory > Local Cache.
        """
        if not task_id:
            return None

        task = self._load_task_from_database(task_id)
        if task:
            task = self._attach_validated_execution_assignment(task)
            self._tasks[task_id] = task
            self._shared_tasks.set(task_id, task)
            return task
        return None

    async def seed_demo_tasks(self, tasks: List[Dict[str, Any]]) -> List[ZentexTask]:
        """Seed local demo tasks through the service boundary."""
        seeded: List[ZentexTask] = []
        for payload in tasks:
            key = str(payload["idempotency_key"])
            existing_id = self._shared_idempotency.get(key)
            if existing_id:
                existing_task = self.get_task(existing_id)
                if existing_task is not None:
                    seeded.append(existing_task)
                continue

            now = datetime.now(timezone.utc)
            status = payload["status"]
            if isinstance(status, str):
                status = TaskStatus(status)
            task_type = payload["task_type"]
            if isinstance(task_type, str):
                task_type = TaskType(task_type)
            task_scope = TaskScope(self._derive_task_scope(payload))
            execution_assignment = self._derive_execution_assignment(payload)

            started_at = None
            completed_at = None
            if status == TaskStatus.IN_PROGRESS:
                started_at = now
            elif status == TaskStatus.DONE:
                started_at = now
                completed_at = now

            task = ZentexTask(
                task_id=str(uuid4())[:8],
                idempotency_key=key,
                title=str(payload["title"]),
                task_type=task_type,
                task_scope=task_scope,
                status=status,
                progress=float(payload.get("progress", 0.0)),
                originator_id=str(payload["originator_id"]),
                target_id=str(payload.get("target_id")) if payload.get("target_id") is not None else None,
                remarks=str(payload["remarks"]) if payload.get("remarks") is not None else None,
                started_at=started_at,
                completed_at=completed_at,
                created_at=now,
                last_updated_at=now,
                execution_assignment=execution_assignment,
            )

            self._shared_tasks.set(task.task_id, task)
            self._shared_idempotency.set(key, task.task_id)
            self._tasks[task.task_id] = task
            self._idempotency_log[key] = task.task_id
            seeded.append(task)

        return seeded


