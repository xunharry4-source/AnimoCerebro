from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceDependencyGraphMixin:
    def add_dependency(self, task_id: str, dependency_id: str) -> ZentexTask:
        """Add a dependency to a task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        dependency = self.get_task(dependency_id)
        if not dependency:
            raise KeyError(f"Dependency task {dependency_id} not found")
            
        if dependency_id in task.depends_on:
            logger.warning(f"Task {task_id} already depends on {dependency_id}")
            return task
            
        # Check for circular dependencies
        if self._would_create_circular_dependency(task_id, dependency_id):
            raise TaskStateError(f"Adding dependency {dependency_id} to {task_id} would create a circular dependency")
            
        task.depends_on.append(dependency_id)
        task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if self.use_database and not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist dependency update for task {task_id}")
        
        self._record_audit(task_id, "DEPENDENCY_ADDED", {
            "dependency_id": dependency_id,
            "new_dependencies": task.depends_on
        })
        
        return task

    def remove_dependency(self, task_id: str, dependency_id: str) -> ZentexTask:
        """Remove a dependency from a task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if dependency_id not in task.depends_on:
            logger.warning(f"Task {task_id} does not depend on {dependency_id}")
            return task
            
        task.depends_on.remove(dependency_id)
        task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(task_id, task)
        self._tasks[task_id] = task
        if self.use_database and not self._sync_task_to_database(task):
            raise TaskStateError(f"Failed to persist dependency removal for task {task_id}")
        
        self._record_audit(task_id, "DEPENDENCY_REMOVED", {
            "dependency_id": dependency_id,
            "remaining_dependencies": task.depends_on
        })
        
        return task

    def get_dependency_tree(self, task_id: str, max_depth: int = 5) -> Dict[str, Any]:
        """Get dependency tree for a task"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        def build_tree(current_id: str, depth: int) -> Dict[str, Any]:
            if depth >= max_depth:
                return {"task_id": current_id, "dependencies": [], "max_depth_reached": True}
                
            current_task = self.get_task(current_id)
            if not current_task:
                return {"task_id": current_id, "dependencies": [], "not_found": True}
                
            dependencies = []
            for dep_id in current_task.depends_on:
                dependencies.append(build_tree(dep_id, depth + 1))
                
            return {
                "task_id": current_id,
                "title": current_task.title,
                "status": current_task.status.value,
                "dependencies": dependencies,
                "depth": depth
            }
            
        return build_tree(task_id, 0)

    def get_dependent_tasks(
        self,
        task_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ZentexTask]:
        """Get tasks that depend on the given task using database filtering."""
        if self.use_database and self._task_dao:
            rows = self._task_dao.list_tasks_depending_on(
                task_id,
                limit=limit,
                offset=offset,
            )
            tasks = [self._dict_to_task(row) for row in rows]
            for task in tasks:
                self._tasks[task.task_id] = task
                self._shared_tasks.set(task.task_id, task)
            return tasks
        tasks = [task for task in self._tasks.values() if task_id in task.depends_on]
        return tasks[max(0, int(offset)): max(0, int(offset)) + max(1, min(int(limit), 500))]

    def can_execute_task(self, task_id: str) -> Dict[str, Any]:
        """Check if a task can be executed based on its dependencies"""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
            
        if task.status != TaskStatus.TODO:
            return {
                "can_execute": False,
                "reason": f"Task is in status: {task.status.value}",
                "dependencies_satisfied": False
            }
            
        unsatisfied_deps = []
        for dep_id in task.depends_on:
            dep_task = self.get_task(dep_id)
            if not dep_task or dep_task.status != TaskStatus.DONE:
                unsatisfied_deps.append({
                    "task_id": dep_id,
                    "status": dep_task.status.value if dep_task else "not_found",
                    "title": dep_task.title if dep_task else "Unknown"
                })
                
        return {
            "can_execute": len(unsatisfied_deps) == 0,
            "reason": "All dependencies satisfied" if not unsatisfied_deps else f"Waiting for {len(unsatisfied_deps)} dependencies",
            "dependencies_satisfied": len(unsatisfied_deps) == 0,
            "unsatisfied_dependencies": unsatisfied_deps
        }

    def _would_create_circular_dependency(self, task_id: str, new_dependency_id: str) -> bool:
        """Check if adding a dependency would create a circular dependency"""
        def check_circular(current_id: str, target_id: str, visited: set) -> bool:
            if current_id == target_id:
                return True
            if current_id in visited:
                return False
                
            visited.add(current_id)
            current_task = self.get_task(current_id)
            if not current_task:
                return False
                
            for dep_id in current_task.depends_on:
                if check_circular(dep_id, target_id, visited):
                    return True
                    
            return False
            
        return check_circular(new_dependency_id, task_id, set())


