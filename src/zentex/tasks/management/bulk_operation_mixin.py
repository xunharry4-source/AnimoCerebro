from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceBulkOperationMixin:
    async def bulk_update_status(self, 
                           task_ids: List[str], 
                           new_status: TaskStatus, 
                           remarks: Optional[str] = None) -> Dict[str, Any]:
        """Bulk update task status"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                updated_task = await self.update_task_status(task_id, new_status, remarks)
                results["success"].append({
                    "task_id": task_id,
                    "previous_status": updated_task.status,
                    "new_status": new_status
                })
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_STATUS_UPDATE", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "new_status": new_status.value,
            "remarks": remarks
        })
        
        return results

    async def bulk_suspend(self, 
                    task_ids: List[str], 
                    reason: str,
                    recovery_conditions: Optional[List[str]] = None) -> Dict[str, Any]:
        """Bulk suspend tasks"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                suspended_task = await self.suspend_task(task_id, reason, recovery_conditions)
                results["success"].append({
                    "task_id": task_id,
                    "status": suspended_task.status
                })
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_SUSPEND", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "reason": reason,
            "recovery_conditions": recovery_conditions
        })
        
        return results

    def bulk_resume(self, task_ids: List[str], remarks: Optional[str] = None) -> Dict[str, Any]:
        """Bulk resume suspended tasks"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                resume_result = self.resume_task(task_id, remarks)
                if asyncio.iscoroutine(resume_result):
                    try:
                        asyncio.get_running_loop()
                    except RuntimeError:
                        resumed_task = asyncio.run(resume_result)
                    else:
                        from concurrent.futures import Future
                        import threading

                        future: Future[ZentexTask] = Future()

                        def _runner() -> None:
                            try:
                                future.set_result(asyncio.run(resume_result))
                            except Exception as exc:  # pragma: no cover
                                future.set_exception(exc)

                        thread = threading.Thread(target=_runner, daemon=True)
                        thread.start()
                        resumed_task = future.result()
                else:
                    resumed_task = resume_result
                results["success"].append({
                    "task_id": task_id,
                    "status": resumed_task.status
                })
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_RESUME", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "remarks": remarks
        })
        
        return {
            **results,
            "requested": len(task_ids),
            "resumed": len(results["success"]),
        }

    def bulk_delete(self, task_ids: List[str], force: bool = False) -> Dict[str, Any]:
        """Bulk delete tasks (with safety checks)"""
        results = {"success": [], "failed": []}
        
        for task_id in task_ids:
            try:
                task = self.get_task(task_id)
                if not task:
                    results["failed"].append({
                        "task_id": task_id,
                        "error": "Task not found"
                    })
                    continue
                    
                # Safety checks
                if not force and task.status in [TaskStatus.IN_PROGRESS]:
                    results["failed"].append({
                        "task_id": task_id,
                        "error": "Cannot delete task in progress without force flag"
                    })
                    continue
                    
                # Check for dependent tasks
                dependent_tasks = self.get_dependent_tasks(task_id, limit=1)
                if dependent_tasks and not force:
                    results["failed"].append({
                        "task_id": task_id,
                        "error": f"Task has {len(dependent_tasks)} dependent tasks"
                    })
                    continue
                    
                if not self.delete_task(task_id, force=force):
                    results["failed"].append({
                        "task_id": task_id,
                        "error": "Official delete_task returned False"
                    })
                    continue
                    
                results["success"].append({
                    "task_id": task_id,
                    "title": task.title
                })
                
            except Exception as e:
                results["failed"].append({
                    "task_id": task_id,
                    "error": str(e)
                })
                
        self._record_audit("bulk_operation", "BULK_DELETE", {
            "task_count": len(task_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "force": force
        })
        
        return results


