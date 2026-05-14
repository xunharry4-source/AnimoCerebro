from __future__ import annotations
"""
Task Route Handlers — Business logic for task management.
Extracted from tasks.py to follow the Facade-First / Thin-Route pattern.
"""
import logging
import json
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from zentex.tasks import TaskManagementService, ZentexTask, TaskStatus

logger = logging.getLogger(__name__)

_ACTION_LABELS = {
    "TASK_CREATED": "任务已创建",
    "TASK_METADATA_UPDATED": "任务元数据已更新",
    "TASK_STATUS_UPDATED": "任务状态已变更",
    "TASK_INTERVENED": "人工干预已记录",
    "TASK_SUSPENDED": "任务已暂停",
    "TASK_RESUMED": "任务已恢复",
    "TASK_DELETED": "任务已删除",
    "TASK_VERIFICATION_COMPLETED": "任务验证已完成",
    "TASK_VERIFICATION_ESCALATED": "任务验证已升级处理",
    "MISSION_DECOMPOSED": "任务目标已拆解",
    "DEPENDENCY_ADDED": "任务依赖已添加",
    "DEPENDENCY_REMOVED": "任务依赖已移除",
    "TASK_HEARTBEAT": "任务心跳已更新",
}

_STATUS_LABELS = {
    "todo": "待调度",
    "in_progress": "执行中",
    "blocked": "调度阻塞",
    "waiting_confirmation": "待确认",
    "done": "已完成",
    "failed": "已失败",
    "suspended": "已暂停",
    "archived": "已归档",
    "cancelled": "已取消",
}

_OPERATOR_LABELS = {
    "system": "系统",
    "web-console": "控制台",
    "web-console-operator": "控制台操作员",
    "ci_acceptance": "真实验收测试",
}


def _parse_audit_details(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def _label_action(action: str) -> str:
    return _ACTION_LABELS.get(action, action.replace("_", " ").title())


def _label_status(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    return _STATUS_LABELS.get(status, status.replace("_", " "))


def _label_operator(operator_id: Optional[str]) -> str:
    if not operator_id:
        return "未知执行方"
    return _OPERATOR_LABELS.get(operator_id, operator_id)


def _details_fragments(details: Any) -> List[str]:
    if not isinstance(details, dict):
        return []

    fragments: List[str] = []
    remarks = details.get("remarks")
    if remarks:
        fragments.append(f"说明：{remarks}")
    title = details.get("title")
    if title:
        fragments.append(f"任务标题：{title}")
    action = details.get("action")
    if action:
        fragments.append(f"干预动作：{action}")
    new_status = details.get("new_status")
    if new_status:
        fragments.append(f"目标状态：{_label_status(str(new_status)) or new_status}")
    subtask_ids = details.get("subtask_ids")
    if isinstance(subtask_ids, list):
        fragments.append(f"子任务数量：{len(subtask_ids)}")
    metadata_updates = details.get("metadata_updates")
    if isinstance(metadata_updates, dict):
        fragments.append(f"更新字段：{', '.join(sorted(metadata_updates.keys()))}")
    if details.get("force") is not None:
        fragments.append(f"强制删除：{'是' if bool(details.get('force')) else '否'}")
    return fragments


def _build_task_log_explanation(row: Dict[str, Any], details: Any) -> Dict[str, Any]:
    action = str(row.get("action") or "")
    old_status = row.get("old_status")
    new_status = row.get("new_status")
    action_label = _label_action(action)
    operator_label = _label_operator(row.get("operator_id"))
    old_status_label = _label_status(old_status)
    new_status_label = _label_status(new_status)
    status_transition = None
    if old_status or new_status:
        status_transition = {
            "from": old_status,
            "from_label": old_status_label,
            "to": new_status,
            "to_label": new_status_label,
            "changed": old_status != new_status,
        }

    detail_fragments = _details_fragments(details)
    if action == "TASK_DELETED":
        summary = f"{action_label}：{old_status_label or old_status or '未知状态'} -> 已删除"
    elif old_status or new_status:
        status_text = f"{old_status_label or old_status or '无状态'} -> {new_status_label or new_status or '无状态'}"
        summary = f"{action_label}：{status_text}"
    else:
        summary = action_label
    if detail_fragments:
        summary = f"{summary}。{detail_fragments[0]}"

    return {
        "action_label": action_label,
        "operator_label": operator_label,
        "status_transition": status_transition,
        "details_text": "；".join(detail_fragments) if detail_fragments else "无补充说明",
        "summary": summary,
    }


def _serialize_task_log_row(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row)
    payload["details"] = _parse_audit_details(payload.get("details"))
    payload.update(_build_task_log_explanation(payload, payload["details"]))
    return payload


def _task_detail_payload(task: ZentexTask, service: TaskManagementService) -> Dict[str, Any]:
    payload = task.model_dump(mode="json")
    suspended = service.get_suspended_task(task.task_id)
    if suspended is None:
        return payload

    suspension_payload = suspended.model_dump(mode="json")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata = dict(metadata)
    metadata["suspension"] = suspension_payload
    metadata["suspension_reason"] = suspended.suspension_reason
    metadata["recovery_conditions"] = list(suspended.recovery_conditions or [])
    metadata["suspension_context"] = dict(suspended.suspension_context or {})
    payload["metadata"] = metadata
    payload["suspension"] = suspension_payload
    return payload


def handle_list_task_logs(
    service: TaskManagementService,
    *,
    task_id: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Return persisted task audit logs with exact database pagination."""
    if not getattr(service, "_db", None):
        raise HTTPException(status_code=503, detail="Task database is unavailable")

    where_parts: list[str] = []
    params: list[Any] = []
    if task_id:
        where_parts.append("task_id = ?")
        params.append(task_id)
    if status:
        where_parts.append("(old_status = ? OR new_status = ? OR action = ?)")
        params.extend([status, status, status])
    if search:
        search_like = f"%{search}%"
        where_parts.append(
            "(task_id LIKE ? OR action LIKE ? OR operator_id LIKE ? OR details LIKE ? OR trace_id LIKE ?)"
        )
        params.extend([search_like] * 5)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    count_rows = service._db.execute_query(
        f"SELECT COUNT(*) AS count FROM task_audit_log {where_sql}",
        tuple(params),
    )
    total = int(count_rows[0]["count"]) if count_rows else 0
    rows = service._db.execute_query(
        f"""
        SELECT id, task_id, action, operator_id, old_status, new_status, details, trace_id, timestamp
        FROM task_audit_log
        {where_sql}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params + [limit, offset]),
    )
    return {
        "task_id": task_id,
        "items": [_serialize_task_log_row(dict(row)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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
            subtasks.append(_task_detail_payload(subtask, service))
    
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
        "task": _task_detail_payload(task, service),
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
            "suspended_subtasks": sum(1 for st in subtasks if st["status"] == "suspended"),
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
        "subtasks": [_task_detail_payload(st, service) for st in subtasks],
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
            subtasks.append(_task_detail_payload(subtask, service))
    
    interventions = [
        receipt for receipt in service._intervention_receipts.values()
        if receipt.get("task_id") == task_id
    ]
    
    return {
        "task": _task_detail_payload(task, service),
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


async def handle_bulk_operation(
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
                await service.update_task_status(task_id, TaskStatus.BLOCKED, remarks=remarks)
            elif action == "resume":
                await service.update_task_status(task_id, TaskStatus.IN_PROGRESS, remarks=remarks)
            elif action == "approve":
                await service.update_task_status(task_id, TaskStatus.DONE, remarks=remarks)
            elif action == "reject":
                await service.update_task_status(task_id, TaskStatus.FAILED, remarks=remarks)
            elif action == "archive":
                await service.update_task_status(task_id, TaskStatus.ARCHIVED, remarks=remarks)
            else:
                results["failed"].append({"task_id": task_id, "error": f"Unknown action: {action}"})
                continue
            
            results["success"].append({"task_id": task_id, "action": action})
        except Exception as e:
            # Bulk operations may continue item-by-item, but they must not hide the
            # traceback for failed items. Recording only a failed row in the payload
            # would fake a diagnosable system while operators lose the real cause.
            logger.exception("Task bulk operation item failed")
            results["failed"].append({"task_id": task_id, "error": str(e)})
    
    return {
        "action": action,
        "total": len(task_ids),
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
        "results": results
    }
