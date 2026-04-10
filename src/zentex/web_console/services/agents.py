"""Agent detail and credit score services."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from zentex.agents.service import AgentCoordinationService
from zentex.tasks.service import TaskManagementService


def calculate_agent_credit_score(
    agent_id: str,
    agent_service: AgentCoordinationService,
    task_service: TaskManagementService,
) -> Dict[str, Any]:
    """
    Calculate credit score for an agent based on multiple dimensions.
    
    Returns a dict with total_score and dimension breakdowns.
    """
    # Get agent asset
    asset = agent_service.manager.get_asset(agent_id)
    if not asset:
        raise KeyError(f"Agent {agent_id} not found")
    
    # Get all tasks for this agent
    all_tasks = [task for task in task_service.list_tasks() if task.target_id == agent_id]
    
    # Calculate dimensions
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.status.value in ["done", "completed"]])
    failed_tasks = len([t for t in all_tasks if t.status.value == "failed"])
    in_progress_tasks = len([t for t in all_tasks if t.status.value == "in_progress"])
    
    # Dimension 1: Task Completion Rate (30% weight)
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 100
    completion_score = min(completion_rate, 100)
    
    # Dimension 2: Response Latency Score (25% weight)
    latency_ms = asset.latency_ms
    if latency_ms is None:
        latency_score = 80  # Default if no data
    elif latency_ms < 100:
        latency_score = 100
    elif latency_ms < 500:
        latency_score = 80
    else:
        latency_score = 60
    
    # Dimension 3: Error Rate Score (20% weight)
    error_rate = (failed_tasks / total_tasks) if total_tasks > 0 else 0
    error_score = max((1 - error_rate) * 100, 0)
    
    # Dimension 4: Audit Compliance Score (15% weight)
    # Based on trust level
    trust_level_scores = {
        "trusted": 100,
        "pending": 70,
        "restricted": 50,
        "revoked": 20,
        "unknown": 50,
    }
    audit_score = trust_level_scores.get(asset.trust_level, 50)
    
    # Dimension 5: Historical Stability Score (10% weight)
    # Based on success rate
    stability_score = asset.success_rate * 100
    
    # Calculate weighted total
    total_score = (
        completion_score * 0.30 +
        latency_score * 0.25 +
        error_score * 0.20 +
        audit_score * 0.15 +
        stability_score * 0.10
    )
    
    return {
        "total_score": round(total_score, 2),
        "dimensions": [
            {
                "name": "任务完成率",
                "name_en": "Task Completion Rate",
                "score": round(completion_score, 2),
                "weight": 0.30,
                "description": f"已完成 {completed_tasks}/{total_tasks} 个任务",
                "trend": "stable",
            },
            {
                "name": "响应延迟评分",
                "name_en": "Response Latency Score",
                "score": round(latency_score, 2),
                "weight": 0.25,
                "description": f"平均延迟 {latency_ms or 'N/A'}ms",
                "trend": "stable",
            },
            {
                "name": "错误率评分",
                "name_en": "Error Rate Score",
                "score": round(error_score, 2),
                "weight": 0.20,
                "description": f"失败率 {error_rate*100:.1f}%",
                "trend": "stable" if error_rate < 0.1 else "down",
            },
            {
                "name": "审计合规评分",
                "name_en": "Audit Compliance Score",
                "score": round(audit_score, 2),
                "weight": 0.15,
                "description": f"信任等级: {asset.trust_level}",
                "trend": "stable",
            },
            {
                "name": "历史稳定性评分",
                "name_en": "Historical Stability Score",
                "score": round(stability_score, 2),
                "weight": 0.10,
                "description": f"成功率 {asset.success_rate*100:.1f}%",
                "trend": "up" if asset.success_rate > 0.9 else "stable",
            },
        ],
        "history": [],  # Will be populated if we track history
    }


def get_agent_statistics(
    agent_id: str,
    task_service: TaskManagementService,
) -> Dict[str, Any]:
    """Get statistics for an agent."""
    all_tasks = [task for task in task_service.list_tasks() if task.target_id == agent_id]
    
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.status.value in ["done", "completed"]])
    failed_tasks = len([t for t in all_tasks if t.status.value == "failed"])
    in_progress_tasks = len([t for t in all_tasks if t.status.value == "in_progress"])
    pending_tasks = len([t for t in all_tasks if t.status.value in ["todo", "blocked", "waiting_confirmation"]])
    
    # Calculate average completion time
    completed_with_time = [
        t for t in all_tasks 
        if t.status.value in ["done", "completed"] and t.started_at and t.completed_at
    ]
    
    if completed_with_time:
        total_completion_seconds = sum(
            (t.completed_at - t.started_at).total_seconds()
            for t in completed_with_time
        )
        avg_completion_time = total_completion_seconds / len(completed_with_time)
    else:
        avg_completion_time = 0
    
    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "in_progress_tasks": in_progress_tasks,
        "pending_tasks": pending_tasks,
        "avg_completion_time": round(avg_completion_time, 2),
        "uptime_percentage": 95.0,  # Placeholder - would need actual uptime tracking
    }


def get_tasks_by_status(
    agent_id: str,
    status_filter: str,
    task_service: TaskManagementService,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "started_at",
    order: str = "desc",
    search: str = "",
    task_type: str = "",
    originator: str = "",
    date_from: str = "",
    date_to: str = "",
) -> Dict[str, Any]:
    """
    Get tasks for an agent filtered by status with pagination and advanced filtering.
    
    Args:
        agent_id: The agent ID
        status_filter: Status to filter by (can be comma-separated for multiple statuses)
        task_service: Task management service
        page: Page number (1-indexed)
        page_size: Items per page
        sort_by: Field to sort by
        order: Sort order (asc or desc)
        search: Search text in task title or ID
        task_type: Filter by task type
        originator: Filter by originator ID
        date_from: Filter from date (ISO format)
        date_to: Filter to date (ISO format)
    
    Returns:
        Dict with tasks list and pagination info
    """
    from datetime import datetime as dt
    
    # Parse status filter (support comma-separated values)
    statuses = [s.strip() for s in status_filter.split(",")]
    
    # Get all tasks for this agent
    all_tasks = [task for task in task_service.list_tasks() if task.target_id == agent_id]
    
    # Filter by status
    filtered_tasks = [t for t in all_tasks if t.status.value in statuses]
    
    # Advanced filters
    if search:
        search_lower = search.lower()
        filtered_tasks = [
            t for t in filtered_tasks
            if search_lower in t.title.lower() or search_lower in t.task_id.lower()
        ]
    
    if task_type:
        filtered_tasks = [t for t in filtered_tasks if t.task_type == task_type]
    
    if originator:
        filtered_tasks = [t for t in filtered_tasks if t.originator_id == originator]
    
    if date_from:
        try:
            from_dt = dt.fromisoformat(date_from.replace('Z', '+00:00'))
            filtered_tasks = [
                t for t in filtered_tasks
                if t.started_at and t.started_at >= from_dt
            ]
        except ValueError:
            pass  # Ignore invalid date format
    
    if date_to:
        try:
            to_dt = dt.fromisoformat(date_to.replace('Z', '+00:00'))
            filtered_tasks = [
                t for t in filtered_tasks
                if t.started_at and t.started_at <= to_dt
            ]
        except ValueError:
            pass  # Ignore invalid date format
    
    # Sort tasks
    reverse = order.lower() == "desc"
    if sort_by == "started_at":
        filtered_tasks.sort(
            key=lambda t: t.started_at or dt.min,
            reverse=reverse
        )
    elif sort_by == "completed_at":
        filtered_tasks.sort(
            key=lambda t: t.completed_at or dt.min,
            reverse=reverse
        )
    elif sort_by == "priority":
        # Assuming tasks have priority field, otherwise use created time
        filtered_tasks.sort(
            key=lambda t: getattr(t, 'priority', 0),
            reverse=reverse
        )
    else:
        # Default sort by started_at
        filtered_tasks.sort(
            key=lambda t: t.started_at or dt.min,
            reverse=reverse
        )
    
    # Pagination
    total = len(filtered_tasks)
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_tasks = filtered_tasks[start_idx:end_idx]
    
    # Convert to dict format
    tasks_data = []
    for task in paginated_tasks:
        tasks_data.append({
            "task_id": task.task_id,
            "subtask_id": task.subtask_id,
            "title": task.title,
            "task_type": task.task_type,
            "status": task.status.value,
            "progress": task.progress,
            "originator_id": task.originator_id,
            "remarks": task.remarks,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "estimated_completion": None,  # Would need estimation logic
            "priority": getattr(task, 'priority', 'normal'),
        })
    
    return {
        "tasks": tasks_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }
    }
