from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from zentex.tasks.models import ZentexTask
from zentex.tasks.models.errors import TaskStateError


def record_task_outcome(
    *,
    outcome_dao: Any,
    task: ZentexTask,
    result: Dict[str, Any],
    verification_result: Any,
) -> Dict[str, Any]:
    if not outcome_dao:
        raise TaskStateError("Task outcome DAO is unavailable")

    verification_payload = (
        verification_result.model_dump(mode="json")
        if hasattr(verification_result, "model_dump")
        else dict(verification_result)
    )
    actual_outcome = result.get("actual_outcome") if isinstance(result, dict) else None
    deviation_report = {
        "summary": verification_payload.get("summary", ""),
        "recommendation": verification_payload.get("recommendation", ""),
        "failed_verifiers": [
            item.get("verifier_id")
            for item in verification_payload.get("verifier_results", [])
            if not item.get("passed")
        ],
    }
    outcome_data = {
        "task_id": task.task_id,
        "trace_id": str(task.metadata.get("trace_id") or ""),
        "objective_profile": task.metadata.get("objective_profile"),
        "evaluation_profile": task.metadata.get("evaluation_profile"),
        "expected_outcome": task.contract.expected_outcome,
        "success_criteria": task.contract.success_criteria,
        "acceptance_conditions": task.contract.acceptance_conditions,
        "risk_assessment": task.contract.risk_assessment,
        "actual_outcome": actual_outcome if actual_outcome is not None else result,
        "deviation_report": deviation_report,
        "verification_result": verification_payload,
        "overall_passed": bool(verification_payload.get("overall_passed")),
        "confidence_score": verification_payload.get("confidence_score"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not outcome_dao.upsert_outcome(outcome_data):
        raise TaskStateError(f"Failed to persist task outcome for {task.task_id}")
    return outcome_data


def write_task_outcome_to_reflection(task_service: Any, reflection_service: Any, task_id: str) -> Dict[str, Any]:
    if not task_id:
        raise TaskStateError("task_id is required for task outcome reflection writeback")
    outcome_dao = _require_outcome_dao(task_service)
    if reflection_service is None or not callable(
        getattr(reflection_service, "record_nine_question_reflection", None)
    ):
        raise TaskStateError("Reflection service with record_nine_question_reflection is required")

    outcome = _require_outcome(task_service, task_id, "reflection")
    existing_reflection_id = str(outcome.get("reflection_id") or "").strip()
    if existing_reflection_id:
        existing_reflection = reflection_service.get_reflection(existing_reflection_id)
        if getattr(existing_reflection, "reflection_id", None) != existing_reflection_id:
            raise TaskStateError(f"Persisted reflection_id does not resolve for task outcome: {task_id}")
        return {"created": False, "reflection_id": existing_reflection_id, "task_outcome": outcome}

    task = _require_task(task_service, task_id, "reflection")
    from zentex.reflection.models import ReflectionType

    trace_id = str(outcome.get("trace_id") or task.metadata.get("trace_id") or "") or None
    actual_outcome = outcome.get("actual_outcome")
    overall_passed = outcome.get("overall_passed")
    summary = f"Task outcome {'passed' if overall_passed else 'failed'} for {task.title}: {actual_outcome}"
    reflection = reflection_service.record_nine_question_reflection(
        subject=f"Task outcome reflection: {task.title}",
        reflection_type=ReflectionType.OUTCOME_REFLECTION,
        trace_id=trace_id,
        context={
            "source": "task_outcome_writeback",
            "question_id": task.metadata.get("question_id"),
            "task_id": task.task_id,
            "task_title": task.title,
            "task_status": _status_value(task),
            "overall_passed": overall_passed,
            "expected_outcome": outcome.get("expected_outcome"),
            "actual_outcome": actual_outcome,
            "success_criteria": outcome.get("success_criteria"),
            "acceptance_conditions": outcome.get("acceptance_conditions"),
            "deviation_report": outcome.get("deviation_report"),
            "verification_result": outcome.get("verification_result"),
            "summary": summary,
        },
    )
    reflection_id = str(getattr(reflection, "reflection_id", "") or "")
    if not reflection_id:
        raise TaskStateError(f"Reflection writeback did not return a reflection_id for task {task_id}")

    queried_reflection = reflection_service.get_reflection(reflection_id)
    if getattr(queried_reflection, "context", {}).get("task_id") != task_id:
        raise TaskStateError(f"Reflection writeback query verification failed for task {task_id}")

    if not outcome_dao.mark_reflection_written(task_id, reflection_id):
        raise TaskStateError(f"Failed to mark task outcome reflection writeback for {task_id}")
    updated_outcome = _verify_updated_outcome(task_service, task_id, "reflection_id", reflection_id)
    if updated_outcome.get("written_back_to_reflection") is not True:
        raise TaskStateError(f"Task outcome reflection flag query verification failed for {task_id}")
    return {"created": True, "reflection_id": reflection_id, "task_outcome": updated_outcome}


def write_task_outcome_to_memory(task_service: Any, memory_service: Any, task_id: str) -> Dict[str, Any]:
    if not task_id:
        raise TaskStateError("task_id is required for task outcome memory writeback")
    outcome_dao = _require_outcome_dao(task_service)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        raise TaskStateError("Memory service with remember is required")
    if not callable(getattr(memory_service, "get_record", None)):
        raise TaskStateError("Memory service with get_record is required")

    outcome = _require_outcome(task_service, task_id, "memory")
    existing_memory_id = str(outcome.get("memory_id") or "").strip()
    if existing_memory_id:
        existing_memory = memory_service.get_record(existing_memory_id)
        if getattr(existing_memory, "memory_id", None) != existing_memory_id:
            raise TaskStateError(f"Persisted memory_id does not resolve for task outcome: {task_id}")
        return {"created": False, "memory_id": existing_memory_id, "task_outcome": outcome}

    task = _require_task(task_service, task_id, "memory")
    trace_id = str(outcome.get("trace_id") or task.metadata.get("trace_id") or "")
    actual_outcome = outcome.get("actual_outcome")
    overall_passed = outcome.get("overall_passed")
    title = f"Task outcome memory: {task.title}"
    summary = f"Task outcome {'passed' if overall_passed else 'failed'} for {task.title}"
    content = (
        f"{summary}\n"
        f"task_id: {task.task_id}\n"
        f"success_criteria: {outcome.get('success_criteria')}\n"
        f"actual_outcome: {actual_outcome}\n"
        f"deviation_report: {outcome.get('deviation_report')}"
    )
    memory = memory_service.remember(
        title=title,
        summary=summary,
        content=content,
        layer="procedural",
        source="task_outcome_writeback",
        trace_id=trace_id or None,
        target_id=task.task_id,
        tags=["task_outcome", "q8", "verified" if overall_passed else "failed"],
        task_id=task.task_id,
        question_id=task.metadata.get("question_id"),
        expected_outcome=outcome.get("expected_outcome"),
        actual_outcome=actual_outcome,
        success_criteria=outcome.get("success_criteria"),
        acceptance_conditions=outcome.get("acceptance_conditions"),
        deviation_report=outcome.get("deviation_report"),
        verification_result=outcome.get("verification_result"),
        overall_passed=overall_passed,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if not memory_id:
        raise TaskStateError(f"Memory writeback did not return a memory_id for task {task_id}")

    queried_memory = memory_service.get_record(memory_id)
    if getattr(queried_memory, "memory_id", None) != memory_id:
        raise TaskStateError(f"Memory writeback query verification failed for task {task_id}")
    if getattr(queried_memory, "target_id", None) != task_id:
        raise TaskStateError(f"Memory writeback target query verification failed for task {task_id}")

    if not outcome_dao.mark_memory_written(task_id, memory_id):
        raise TaskStateError(f"Failed to mark task outcome memory writeback for {task_id}")
    updated_outcome = _verify_updated_outcome(task_service, task_id, "memory_id", memory_id)
    if updated_outcome.get("written_back_to_memory") is not True:
        raise TaskStateError(f"Task outcome memory flag query verification failed for {task_id}")
    return {"created": True, "memory_id": memory_id, "task_outcome": updated_outcome}


def write_task_outcome_to_learning(task_service: Any, learning_service: Any, task_id: str) -> Dict[str, Any]:
    if not task_id:
        raise TaskStateError("task_id is required for task outcome learning writeback")
    outcome_dao = _require_outcome_dao(task_service)
    if learning_service is None or not callable(
        getattr(learning_service, "record_nine_question_learning", None)
    ):
        raise TaskStateError("Learning service with record_nine_question_learning is required")
    if not callable(getattr(learning_service, "query_overall_records", None)):
        raise TaskStateError("Learning service with query_overall_records is required")

    outcome = _require_outcome(task_service, task_id, "learning")
    existing_learning_trace_id = str(outcome.get("learning_trace_id") or "").strip()
    if existing_learning_trace_id:
        existing_records = learning_service.query_overall_records(limit=20, trace_id=existing_learning_trace_id)
        if not any(record.detail.get("task_id") == task_id for record in existing_records):
            raise TaskStateError(f"Persisted learning_trace_id does not resolve for task outcome: {task_id}")
        return {"created": False, "learning_trace_id": existing_learning_trace_id, "task_outcome": outcome}

    task = _require_task(task_service, task_id, "learning")
    source_trace_id = str(outcome.get("trace_id") or task.metadata.get("trace_id") or "")
    overall_passed = outcome.get("overall_passed")
    actual_outcome = outcome.get("actual_outcome")
    summary = f"Learned from task outcome {'passed' if overall_passed else 'failed'}: {task.title}"
    learning = learning_service.record_nine_question_learning(
        question_id=str(task.metadata.get("question_id") or "q8"),
        learning_kind="task_outcome_writeback",
        trace_id=source_trace_id or task.task_id,
        detail={
            "summary": summary,
            "source": "task_outcome_writeback",
            "source_trace_id": source_trace_id,
            "task_id": task.task_id,
            "task_title": task.title,
            "task_status": _status_value(task),
            "overall_passed": overall_passed,
            "expected_outcome": outcome.get("expected_outcome"),
            "actual_outcome": actual_outcome,
            "success_criteria": outcome.get("success_criteria"),
            "acceptance_conditions": outcome.get("acceptance_conditions"),
            "deviation_report": outcome.get("deviation_report"),
            "verification_result": outcome.get("verification_result"),
            "question_driver_refs": [str(task.metadata.get("question_id") or "q8")],
        },
    )
    learning_trace_id = str(getattr(learning, "trace_id", "") or "")
    if not learning_trace_id:
        raise TaskStateError(f"Learning writeback did not return a trace_id for task {task_id}")

    queried_records = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matching_records = [record for record in queried_records if record.detail.get("task_id") == task_id]
    if len(matching_records) != 1:
        raise TaskStateError(f"Learning writeback query verification failed for task {task_id}")
    if matching_records[0].detail.get("actual_outcome") != actual_outcome:
        raise TaskStateError(f"Learning writeback actual outcome mismatch for task {task_id}")

    if not outcome_dao.mark_learning_written(task_id, learning_trace_id):
        raise TaskStateError(f"Failed to mark task outcome learning writeback for {task_id}")
    updated_outcome = _verify_updated_outcome(task_service, task_id, "learning_trace_id", learning_trace_id)
    if updated_outcome.get("written_back_to_learning") is not True:
        raise TaskStateError(f"Task outcome learning flag query verification failed for {task_id}")
    return {"created": True, "learning_trace_id": learning_trace_id, "task_outcome": updated_outcome}


def _require_outcome_dao(task_service: Any) -> Any:
    outcome_dao = getattr(task_service, "_outcome_dao", None)
    if not outcome_dao:
        raise TaskStateError("Task outcome DAO is unavailable")
    return outcome_dao


def _require_outcome(task_service: Any, task_id: str, target: str) -> Dict[str, Any]:
    outcome = task_service.get_task_outcome(task_id)
    if outcome is None:
        raise TaskStateError(f"Task outcome not found for {target} writeback: {task_id}")
    return outcome


def _require_task(task_service: Any, task_id: str, target: str) -> ZentexTask:
    task = task_service.get_task(task_id)
    if task is None:
        raise TaskStateError(f"Task not found for {target} writeback: {task_id}")
    return task


def _verify_updated_outcome(
    task_service: Any,
    task_id: str,
    field_name: str,
    expected_value: str,
) -> Dict[str, Any]:
    updated_outcome = task_service.get_task_outcome(task_id)
    if not updated_outcome or updated_outcome.get(field_name) != expected_value:
        raise TaskStateError(f"Task outcome {field_name} marker query verification failed for {task_id}")
    return updated_outcome


def _status_value(task: ZentexTask) -> str:
    return task.status.value if hasattr(task.status, "value") else str(task.status)
