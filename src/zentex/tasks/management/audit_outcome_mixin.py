from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceAuditOutcomeMixin:
    def _record_audit(self, task_id: str, action: str, details: Dict[str, Any]):
        if self.transcript_store is None or not callable(getattr(self.transcript_store, "write_entry", None)):
            return
        normalized_details = self._normalize_audit_value(details)
        self.transcript_store.write_entry(
            session_id="task-management-audit",
            turn_id=str(uuid4()),
            entry_type=AuditEventType.PLUGIN_AUDIT_EVENT,
            source="TaskManagementService",
            trace_id=f"task-audit:{task_id}:{action.lower()}",
            payload={
                "task_id": task_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": normalized_details
            }
        )

    def _normalize_audit_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
            return self._normalize_audit_value(value.model_dump(mode="json"))
        if hasattr(value, "value"):
            return self._normalize_audit_value(value.value)
        if isinstance(value, dict):
            return {str(k): self._normalize_audit_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._normalize_audit_value(v) for v in value]
        return str(value)

    def _record_task_outcome(
        self,
        *,
        task: ZentexTask,
        result: Dict[str, Any],
        verification_result: Any,
    ) -> Dict[str, Any]:
        outcome = task_outcomes.record_task_outcome(
            outcome_dao=self._outcome_dao,
            task=task,
            result=result,
            verification_result=verification_result,
        )
        audit_service = self._workflow_audit_service
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        trace_id = str(outcome.get("trace_id") or metadata.get("trace_id") or task.task_id)
        session_id = str(metadata.get("session_id") or task.originator_id or trace_id)
        if audit_service is not None:
            try:
                from zentex.audit.workflow_events import record_workflow_node_event

                verification_payload = self._normalize_audit_value(outcome.get("verification_result", {}))
                record_workflow_node_event(
                    audit_service=audit_service,
                    event_type="task_outcome_recorded",
                    node_id="task-outcome-recorded",
                    node_name="Task outcome recorded",
                    status="succeeded" if outcome.get("overall_passed") is True else "failed",
                    trace_id=trace_id,
                    session_id=session_id,
                    task_id=task.task_id,
                    output_summary={
                        "overall_passed": outcome.get("overall_passed"),
                        "task_status": outcome.get("task_status"),
                        "has_actual_outcome": "actual_outcome" in outcome,
                        "verification_passed": verification_payload.get("overall_passed")
                        if isinstance(verification_payload, dict)
                        else None,
                    },
                    evidence_ref=f"task_outcome:{task.task_id}:{trace_id}",
                    source="zentex.tasks.management.task_management_service",
                )
                record_workflow_node_event(
                    audit_service=audit_service,
                    event_type="verification_finished",
                    node_id="task-outcome-recorded",
                    node_name="Task outcome verification finished",
                    status="succeeded" if outcome.get("overall_passed") is True else "failed",
                    trace_id=trace_id,
                    session_id=session_id,
                    task_id=task.task_id,
                    output_summary={
                        "overall_passed": outcome.get("overall_passed"),
                        "verification_passed": verification_payload.get("overall_passed")
                        if isinstance(verification_payload, dict)
                        else None,
                        "verifier_count": len(verification_payload.get("verifier_results") or [])
                        if isinstance(verification_payload, dict)
                        else 0,
                    },
                    evidence_ref=f"task_outcome:{task.task_id}:{trace_id}",
                    source="zentex.tasks.management.task_management_service",
                )
            except Exception:
                logger.warning("Failed to record task_outcome_recorded workflow audit event", exc_info=True)
        return outcome

    def get_task_outcome(self, task_id: str) -> Optional[Dict[str, Any]]:
        if not self._outcome_dao:
            raise RuntimeError("Task outcome DAO is unavailable")
        return self._outcome_dao.get_outcome(task_id)

    def write_task_outcome_to_reflection(self, reflection_service: Any, task_id: str) -> Dict[str, Any]:
        return task_outcomes.write_task_outcome_to_reflection(self, reflection_service, task_id)

    def write_task_outcome_to_memory(self, memory_service: Any, task_id: str) -> Dict[str, Any]:
        return task_outcomes.write_task_outcome_to_memory(self, memory_service, task_id)

    def write_task_outcome_to_learning(self, learning_service: Any, task_id: str) -> Dict[str, Any]:
        return task_outcomes.write_task_outcome_to_learning(self, learning_service, task_id)


