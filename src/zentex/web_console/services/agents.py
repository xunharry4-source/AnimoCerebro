"""
Agent Service Thin Adapter — Web Console Layer.

ARCHITECTURE ROLE:
1. Thin Facade: Directs API requests to core domain services (AgentCoordinationService).
2. Zero Business Logic: Strictly prohibited from implementing calculations, scores, or analytical rules.
3. Responsibility:
   - [Query Condition Preparation]: Parsing/validating HTTP parameters into technical domain objects.
   - [Result Splicing]: Mapping complex technical domain objects into frontend-friendly API contracts.

DECOUPLING POLICY (Zentex Codex §2):
This module must remain a 'Logic-Free Zone'. Any evolution of agent metrics, credit scoring 
algorithms, or task aggregation rules must be implemented in `zentex.agents.service`.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime

from zentex.agents.service import AgentCoordinationService
from zentex.tasks.service import TaskManagementService

def calculate_agent_credit_score(
    agent_id: str,
    agent_service: AgentCoordinationService,
    task_service: TaskManagementService,
) -> Dict[str, Any]:
    """Thin adapter for core credit score calculation."""
    return agent_service.calculate_credit_score(agent_id, task_service)

def get_agent_statistics(
    agent_id: str,
    task_service: TaskManagementService,
) -> Dict[str, Any]:
    """Thin adapter for core statistics aggregation."""
    # We need the agent_service to call its own stats logic
    # In web console routers, both services are usually available via dependency injection
    from zentex.agents.service import get_service as get_agent_service
    agent_service = get_agent_service()
    return agent_service.get_statistics(agent_id, task_service)

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
    Thin adapter for advanced task querying.
    Zero business logic: only parses date strings and delegating to core.
    """
    from zentex.agents.service import get_service as get_agent_service
    agent_service = get_agent_service()
    
    # Parse dates (Query Condition Preparation)
    dt_from = None
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        except ValueError:
            pass
            
    dt_to = None
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        except ValueError:
            pass

    # Call core query logic
    result = agent_service.query_agent_tasks(
        agent_id=agent_id,
        task_service=task_service,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
        search=search,
        task_type=task_type,
        originator=originator,
        date_from=dt_from,
        date_to=dt_to
    )
    
    # Result Splicing (Mapping core tasks to UI contract)
    tasks_data = []
    for task in result["tasks"]:
        tasks_data.append({
            "task_id": task.task_id,
            "subtask_id": task.subtask_id,
            "title": task.title,
            "task_type": task.task_type.value,
            "status": task.status.value,
            "progress": task.progress,
            "originator_id": task.originator_id,
            "remarks": task.remarks,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "estimated_completion": None,
            "priority": getattr(task, 'priority', 'normal'),
        })
        
    return {
        "tasks": tasks_data,
        "pagination": result["pagination"]
    }
