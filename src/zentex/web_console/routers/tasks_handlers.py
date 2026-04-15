"""
Task Route Handlers — Business logic for task management.
Extracted from tasks.py to follow the Facade-First / Thin-Route pattern.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from zentex.tasks.service import TaskManagementService, ZentexTask, TaskStatus


def handle_get_task_detail(
    task_id: str,
    service: TaskManagementService,
) -> Dict[str, Any]:
    """Handle retrieving complete task details."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    subtasks = []
    for subtask_id in task.subtask_ids:
        subtask = service.get_task(subtask_id)
        if subtask:
            subtasks.append(subtask.model_dump(mode="json"))
    
    dependencies = []
    for dep_id in task.depends_on:
        dep_task = service.get_task(dep_id)
        if dep_task:
            dependencies.append({
                "task_id": dep_id,
                "title": dep_task.title,
                "status": dep_task.status.value
            })
    
    dependent_tasks = service.get_dependent_tasks(task_id)
    dependents = [{
        "task_id": t.task_id,
        "title": t.title,
        "status": t.status.value
    } for t in dependent_tasks]
    
    interventions = [
        receipt for receipt in service._intervention_receipts.values()
        if receipt.get("task_id") == task_id
    ]
    
    return {
        "task": task.model_dump(mode="json"),
        "subtasks": subtasks,
        "subtask_count": len(subtasks),
        "dependencies": dependencies,
        "dependents": dependents,
        "interventions": interventions,
        "statistics": {
            "total_subtasks": len(subtasks),
            "completed_subtasks": sum(1 for st in subtasks if st["status"] == "done"),
            "in_progress_subtasks": sum(1 for st in subtasks if st["status"] == "in_progress"),
            "pending_subtasks": sum(1 for st in subtasks if st["status"] in ["todo", "blocked"]),
            "failed_subtasks": sum(1 for st in subtasks if st["status"] == "failed")
        }
    }


def handle_get_subtasks(
    task_id: str,
    service: TaskManagementService,
    status_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle retrieving subtasks with filtering and stats."""
    parent_task = service.get_task(task_id)
    if not parent_task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    subtasks = []
    for subtask_id in parent_task.subtask_ids:
        subtask = service.get_task(subtask_id)
        if subtask:
            if status_filter:
                try:
                    status_enum = TaskStatus(status_filter)
                    if subtask.status == status_enum:
                        subtasks.append(subtask)
                except ValueError:
                    subtasks.append(subtask)
            else:
                subtasks.append(subtask)
    
    stats = {
        "total": len(parent_task.subtask_ids),
        "returned": len(subtasks),
        "by_status": {}
    }
    for st in subtasks:
        status = st.status.value
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
    
    return {
        "parent_task_id": task_id,
        "subtasks": [st.model_dump(mode="json") for st in subtasks],
        "statistics": stats
    }


def handle_get_execution_history(
    task_id: str,
    service: TaskManagementService,
) -> Dict[str, Any]:
    """Handle retrieving task execution history and audit trail."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    subtasks = []
    for subtask_id in task.subtask_ids:
        subtask = service.get_task(subtask_id)
        if subtask:
            subtasks.append(subtask.model_dump(mode="json"))
    
    interventions = [
        receipt for receipt in service._intervention_receipts.values()
        if receipt.get("task_id") == task_id
    ]
    
    return {
        "task": task.model_dump(mode="json"),
        "subtasks": subtasks,
        "interventions": interventions,
        "audit_trail": {
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "last_updated_at": task.last_updated_at.isoformat(),
            "status_changes": len(interventions),
            "total_interventions": len(interventions)
        }
    }


def handle_bulk_operation(
    service: TaskManagementService,
    task_ids: List[str],
    action: str,
    remarks: str = "",
) -> Dict[str, Any]:
    """Handle bulk operations on tasks."""
    results = {"success": [], "failed": []}
    
    for task_id in task_ids:
        try:
            if action == "pause":
                service.update_task_status(task_id, TaskStatus.BLOCKED, remarks=remarks)
            elif action == "resume":
                service.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks=remarks)
            elif action == "approve":
                service.update_task_status(task_id, TaskStatus.DONE, remarks=remarks)
            elif action == "reject":
                service.update_task_status(task_id, TaskStatus.FAILED, remarks=remarks)
            elif action == "archive":
                service.update_task_status(task_id, TaskStatus.ARCHIVED, remarks=remarks)
            else:
                results["failed"].append({"task_id": task_id, "error": f"Unknown action: {action}"})
                continue
            
            results["success"].append({"task_id": task_id, "action": action})
        except Exception as e:
            results["failed"].append({"task_id": task_id, "error": str(e)})
    
    return {
        "action": action,
        "total": len(task_ids),
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
        "results": results
    }
