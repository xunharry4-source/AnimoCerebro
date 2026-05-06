from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceRecoveryStatisticsMixin:
    async def record_blocked_task_recovery_experience(
        self,
        *,
        task_id: str,
        trace_id: str,
        session_id: str,
        error_code: str,
        block_reason: str,
        recovery_advice: str,
    ) -> Dict[str, Any]:
        task = self.get_task(task_id)
        if task is None:
            return {"status": "skipped", "reason": "task_missing", "task_id": task_id}

        result: Dict[str, Any] = {
            "status": "succeeded",
            "task_id": task_id,
            "trace_id": trace_id,
            "session_id": session_id,
            "error_code": error_code,
            "block_reason": block_reason,
            "recovery_advice": recovery_advice,
        }
        if self._learning_service is not None and callable(getattr(self._learning_service, "record_nine_question_learning", None)):
            learning = self._learning_service.record_nine_question_learning(
                question_id=str(task.metadata.get("question_id") or "q8"),
                learning_kind="blocked_task_recovery",
                trace_id=trace_id,
                detail={
                    "summary": f"Blocked task recovery for {task.title}: {error_code}",
                    "source": "blocked_task_recovery",
                    "source_trace_id": trace_id,
                    "task_id": task_id,
                    "task_title": task.title,
                    "task_status": "blocked",
                    "overall_passed": False,
                    "error_code": error_code,
                    "block_reason": block_reason,
                    "best_practice": "Run health probe before dispatch and register replacement capability before retry.",
                    "avoid_pattern": "Do not silently downgrade to an internal rule or mark blocked work as successful when no healthy authorized replacement exists.",
                    "recommended_next_action": recovery_advice,
                    "actual_outcome": {
                        "blocked": True,
                        "error_code": error_code,
                        "block_reason": block_reason,
                    },
                },
            )
            result["learning_trace_id"] = str(getattr(learning, "trace_id", "") or "")
        if self._reflection_service is not None and callable(getattr(self._reflection_service, "record_nine_question_reflection", None)):
            from zentex.reflection.models import ReflectionType

            reflection = self._reflection_service.record_nine_question_reflection(
                subject=f"Blocked task recovery reflection: {task.title}",
                reflection_type=ReflectionType.OUTCOME_REFLECTION,
                trace_id=trace_id,
                context={
                    "source": "blocked_task_recovery",
                    "session_id": session_id,
                    "task_id": task_id,
                    "task_title": task.title,
                    "task_status": "blocked",
                    "overall_passed": False,
                    "error_code": error_code,
                    "block_reason": block_reason,
                    "root_cause": "The selected executor was unavailable and no healthy authorized replacement was registered.",
                    "actionable_adjustment": recovery_advice,
                    "actual_outcome": {
                        "blocked": True,
                        "error_code": error_code,
                        "block_reason": block_reason,
                    },
                    "summary": f"Blocked because {block_reason}; next run must health probe and register a replacement first.",
                },
            )
            result["reflection_id"] = str(getattr(reflection, "reflection_id", "") or "")
        if callable(getattr(self, "update_task_metadata", None)):
            await self.update_task_metadata(
                task_id,
                {"blocked_recovery_experience": result},
                remarks="Blocked task recovery learning/reflection recorded",
            )
        if self._workflow_audit_service is not None:
            from zentex.audit.workflow_events import record_workflow_node_event

            if result.get("learning_trace_id"):
                record_workflow_node_event(
                    audit_service=self._workflow_audit_service,
                    event_type="learning_writeback_finished",
                    node_id="blocked-task-recovery",
                    node_name="Blocked task recovery learning",
                    status="succeeded",
                    trace_id=trace_id,
                    session_id=session_id,
                    task_id=task_id,
                    output_summary={"learning_trace_id": result.get("learning_trace_id"), "error_code": error_code},
                    evidence_ref=f"blocked_recovery:{task_id}:{trace_id}",
                    source="zentex.tasks.management.task_management_service",
                )
            if result.get("reflection_id"):
                record_workflow_node_event(
                    audit_service=self._workflow_audit_service,
                    event_type="reflection_writeback_finished",
                    node_id="blocked-task-recovery",
                    node_name="Blocked task recovery reflection",
                    status="succeeded",
                    trace_id=trace_id,
                    session_id=session_id,
                    task_id=task_id,
                    output_summary={"reflection_id": result.get("reflection_id"), "error_code": error_code},
                    evidence_ref=f"blocked_recovery:{task_id}:{trace_id}",
                    source="zentex.tasks.management.task_management_service",
                )
        return result

    async def _run_automatic_outcome_maintenance_hook(self, task_id: str) -> Dict[str, Any]:
        if not any((self._memory_service, self._learning_service, self._reflection_service)):
            return {
                "status": "skipped",
                "reason": "outcome_maintenance_services_not_attached",
                "task_id": task_id,
            }
        from zentex.tasks.maintenance.outcome_maintenance import run_automatic_outcome_maintenance

        return await run_automatic_outcome_maintenance(
            task_service=self,
            task_id=task_id,
            memory_service=self._memory_service,
            learning_service=self._learning_service,
            reflection_service=self._reflection_service,
            audit_service=self._workflow_audit_service,
        )
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计信息，支持数据库和内存两种模式"""
        try:
            # Use database statistics if available
            if self.use_database and self._task_dao:
                db_stats = self._task_dao.get_task_statistics()
                
                # Get suspended tasks count
                suspended_count = 0
                if self._suspended_dao:
                    suspended_count = self._suspended_dao.count_suspended_tasks()
                
                # Calculate active tasks
                active_tasks = db_stats.get('todo_count', 0) + db_stats.get('in_progress_count', 0)
                
                return {
                    "total_tasks": db_stats.get('total_tasks', 0),
                    "tasks_by_status": {
                        "todo": db_stats.get('todo_count', 0),
                        "in_progress": db_stats.get('in_progress_count', 0),
                        "done": db_stats.get('done_count', 0),
                        "failed": db_stats.get('failed_count', 0),
                        "suspended": db_stats.get('suspended_count', 0),
                        "blocked": db_stats.get('blocked_count', 0),
                    },
                    "tasks_by_priority": {},  # Would need additional query
                    "tasks_by_type": {},  # Would need additional query
                    "tasks_today": 0,  # Would need date-based query
                    "suspended_tasks": suspended_count,
                    "active_tasks": active_tasks,
                    "completed_tasks": db_stats.get('done_count', 0),
                    "failed_tasks": db_stats.get('failed_count', 0),
                    "avg_progress": db_stats.get('avg_progress', 0.0),
                    "source": "database"
                }
            
            # Fallback to in-memory statistics
            tasks = list(self._tasks.values())
            
            # 基础统计
            total_tasks = len(tasks)
            
            # 按状态统计
            status_counts = {}
            for task in tasks:
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # 按优先级统计
            priority_counts = {}
            for task in tasks:
                priority = task.priority.value
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            # 按类型统计
            type_counts = {}
            for task in tasks:
                task_type = task.task_type.value
                type_counts[task_type] = type_counts.get(task_type, 0) + 1
            
            # 时间统计
            from datetime import datetime, timezone, timedelta
            today = datetime.now(timezone.utc).date()
            today_tasks = len([t for t in tasks if t.created_at.date() == today])
            
            # 挂起任务统计
            suspended_count = len(self._suspended_tasks)
            
            return {
                "total_tasks": total_tasks,
                "tasks_by_status": status_counts,
                "tasks_by_priority": priority_counts,
                "tasks_by_type": type_counts,
                "tasks_today": today_tasks,
                "suspended_tasks": suspended_count,
                "active_tasks": status_counts.get("todo", 0) + status_counts.get("in_progress", 0),
                "completed_tasks": status_counts.get("done", 0),
                "failed_tasks": status_counts.get("failed", 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get task statistics: {e}")
            return {
                "total_tasks": 0,
                "error": str(e)
            }

    # === Verification Methods ===
    

