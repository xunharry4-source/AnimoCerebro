from __future__ import annotations

from typing import Any, Dict, List


def q9_candidate_registry_payload(candidates: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "owner_ref": candidate.owner_ref,
            "executor_type": candidate.executor_type,
            "executor_id": candidate.executor_id,
            "label": candidate.label,
            "capabilities": list(candidate.capabilities or []),
            "metadata": dict(candidate.metadata or {}),
        }
        for candidate in candidates
    ]


def q9_existing_dependency_graph(existing_children: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "task_id": task.task_id,
            "subtask_id": task.subtask_id,
            "depends_on": list(task.depends_on or []),
            "step_index": int((task.metadata or {}).get("q9_blueprint_step_index", 0)),
        }
        for task in existing_children
    ]


def q9_existing_assignment_results(existing_children: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "task_id": task.task_id,
            "subtask_id": task.subtask_id,
            "status": task.status.value,
            "assignment_status": (task.metadata or {}).get("assignment_status"),
            "owner_ref": (task.metadata or {}).get("owner_ref") or task.target_id or "",
            "missing_resources": (task.metadata or {}).get("g31a_assignment", {}).get("missing_resources", []),
            "negotiation_id": (task.metadata or {}).get("g5_active_negotiation_id"),
        }
        for task in existing_children
    ]


def q9_created_dependency_graph(created: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "task_id": task.task_id,
            "subtask_id": task.subtask_id,
            "depends_on": list(task.depends_on or []),
            "step_index": int((task.metadata or {}).get("q9_blueprint_step_index", 0)),
        }
        for task in created
    ]


def q9_assignment_result_payload(child: Any, decision: Any) -> Dict[str, Any]:
    return {
        "task_id": child.task_id,
        "subtask_id": child.subtask_id,
        "status": child.status.value,
        "assignment_status": decision.status,
        "owner_ref": decision.owner_ref,
        "missing_resources": decision.missing_resources,
        "negotiation_id": (decision.negotiation or {}).get("negotiation_id") if decision.negotiation else None,
    }


__all__ = [
    "q9_candidate_registry_payload",
    "q9_existing_dependency_graph",
    "q9_existing_assignment_results",
    "q9_created_dependency_graph",
    "q9_assignment_result_payload",
]
