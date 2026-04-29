from __future__ import annotations

from typing import Any


class Q8ReplayIntegrityError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 replay integrity check failed")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _append_writeback_record_failure(
    failures: list[dict[str, Any]],
    *,
    reason: str,
    task_id: str,
    record_id: str | None = None,
    error: Exception | None = None,
) -> None:
    failure: dict[str, Any] = {"reason": reason, "task_id": task_id}
    if record_id:
        failure["record_id"] = record_id
    if error is not None:
        failure["error_type"] = type(error).__name__
        failure["error_message"] = str(error)
    failures.append(failure)


def _verify_reflection_writeback_record(reflection_service: Any, task_id: str, reflection_id: Any) -> bool:
    reflection_id = str(reflection_id or "").strip()
    if not reflection_id:
        raise LookupError("reflection_id is empty")
    if reflection_service is None or not callable(getattr(reflection_service, "get_reflection", None)):
        raise RuntimeError("reflection_service.get_reflection is required")
    reflection = reflection_service.get_reflection(reflection_id)
    context = _as_dict(getattr(reflection, "context", None))
    if getattr(reflection, "reflection_id", None) != reflection_id:
        raise LookupError(f"reflection record {reflection_id} did not resolve")
    if context.get("task_id") != task_id:
        raise LookupError(f"reflection record {reflection_id} does not belong to task {task_id}")
    return True


def _verify_memory_writeback_record(memory_service: Any, task_id: str, memory_id: Any) -> bool:
    memory_id = str(memory_id or "").strip()
    if not memory_id:
        raise LookupError("memory_id is empty")
    if memory_service is None or not callable(getattr(memory_service, "get_record", None)):
        raise RuntimeError("memory_service.get_record is required")
    memory = memory_service.get_record(memory_id)
    if getattr(memory, "memory_id", None) != memory_id:
        raise LookupError(f"memory record {memory_id} did not resolve")
    payload = _as_dict(getattr(memory, "payload", None))
    if getattr(memory, "target_id", None) != task_id and payload.get("task_id") != task_id:
        raise LookupError(f"memory record {memory_id} does not belong to task {task_id}")
    return True


def _verify_learning_writeback_record(learning_service: Any, task_id: str, learning_trace_id: Any) -> bool:
    learning_trace_id = str(learning_trace_id or "").strip()
    if not learning_trace_id:
        raise LookupError("learning_trace_id is empty")
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise RuntimeError("learning_service.query_overall_records is required")
    records = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    if not any(_as_dict(getattr(record, "detail", None)).get("task_id") == task_id for record in records):
        raise LookupError(f"learning record {learning_trace_id} does not belong to task {task_id}")
    return True


def build_q8_replay_integrity_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    require_writebacks: bool = False,
    reflection_service: Any = None,
    memory_service: Any = None,
    learning_service: Any = None,
) -> dict[str, Any]:
    if task_service is None:
        raise Q8ReplayIntegrityError([{"reason": "task_service_missing"}])
    if expected_task_count <= 0:
        raise Q8ReplayIntegrityError([{"reason": "expected_task_count_must_be_positive"}])

    list_tasks = getattr(task_service, "list_tasks", None)
    get_task_outcome = getattr(task_service, "get_task_outcome", None)
    if not callable(list_tasks) or not callable(get_task_outcome):
        raise Q8ReplayIntegrityError([{"reason": "task_service_query_methods_missing"}])

    tasks = list(
        list_tasks(
            metadata_filters={
                "source": "nine_questions.q8",
                "session_id": session_id,
            }
        )
        or []
    )
    tasks.sort(key=lambda item: str(_task_value(item, "title") or ""))

    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append(
            {
                "reason": "task_count_mismatch",
                "expected": expected_task_count,
                "actual": len(tasks),
            }
        )

    seen_task_ids: set[str] = set()
    seen_trace_ids: set[str] = set()
    receipts: list[dict[str, Any]] = []
    writeback_counts = {
        "reflection": 0,
        "memory": 0,
        "learning": 0,
    }
    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        title = str(_task_value(task, "title") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        trace_id = str(metadata.get("trace_id") or "").strip()
        q9_trace_id = str(_as_dict(metadata.get("phase_a_evaluation")).get("source_trace_id") or "").strip()
        outcome = get_task_outcome(task_id)
        outcome = _as_dict(outcome)

        if not task_id:
            failures.append({"reason": "task_id_missing", "title": title})
        if task_id in seen_task_ids:
            failures.append({"reason": "duplicate_task_id", "task_id": task_id})
        seen_task_ids.add(task_id)

        if not trace_id:
            failures.append({"reason": "q8_trace_id_missing", "task_id": task_id})
        else:
            seen_trace_ids.add(trace_id)

        if metadata.get("source") != "nine_questions.q8":
            failures.append({"reason": "source_mismatch", "task_id": task_id, "source": metadata.get("source")})
        if metadata.get("session_id") != session_id:
            failures.append({"reason": "session_id_mismatch", "task_id": task_id, "session_id": metadata.get("session_id")})
        if not q9_trace_id:
            failures.append({"reason": "q9_trace_id_missing", "task_id": task_id})

        if not outcome:
            failures.append({"reason": "task_outcome_missing", "task_id": task_id})
            continue
        if outcome.get("trace_id") != trace_id:
            failures.append(
                {
                    "reason": "outcome_trace_mismatch",
                    "task_id": task_id,
                    "task_trace_id": trace_id,
                    "outcome_trace_id": outcome.get("trace_id"),
                }
            )
        if outcome.get("overall_passed") is not True:
            failures.append({"reason": "outcome_not_passed", "task_id": task_id, "overall_passed": outcome.get("overall_passed")})
        actual_outcome = _as_dict(outcome.get("actual_outcome"))
        if actual_outcome.get("task_id") != task_id:
            failures.append(
                {
                    "reason": "actual_outcome_task_id_mismatch",
                    "task_id": task_id,
                    "actual_task_id": actual_outcome.get("task_id"),
                }
            )
        verification_result = _as_dict(outcome.get("verification_result"))
        if verification_result.get("overall_passed") is not True:
            failures.append({"reason": "verification_not_passed", "task_id": task_id})
        if not verification_result.get("verifier_results"):
            failures.append({"reason": "verifier_results_missing", "task_id": task_id})

        written_back_to_reflection = outcome.get("written_back_to_reflection") is True
        written_back_to_memory = outcome.get("written_back_to_memory") is True
        written_back_to_learning = outcome.get("written_back_to_learning") is True
        reflection_verified = False
        memory_verified = False
        learning_verified = False
        if written_back_to_reflection:
            writeback_counts["reflection"] += 1
        if written_back_to_memory:
            writeback_counts["memory"] += 1
        if written_back_to_learning:
            writeback_counts["learning"] += 1

        if require_writebacks:
            if not written_back_to_reflection:
                failures.append({"reason": "reflection_writeback_missing", "task_id": task_id})
            if not written_back_to_memory:
                failures.append({"reason": "memory_writeback_missing", "task_id": task_id})
            if not written_back_to_learning:
                failures.append({"reason": "learning_writeback_missing", "task_id": task_id})

            if written_back_to_reflection:
                try:
                    reflection_verified = _verify_reflection_writeback_record(
                        reflection_service,
                        task_id,
                        outcome.get("reflection_id"),
                    )
                except Exception as exc:
                    _append_writeback_record_failure(
                        failures,
                        reason="reflection_writeback_record_invalid",
                        task_id=task_id,
                        record_id=str(outcome.get("reflection_id") or ""),
                        error=exc,
                    )
            if written_back_to_memory:
                try:
                    memory_verified = _verify_memory_writeback_record(
                        memory_service,
                        task_id,
                        outcome.get("memory_id"),
                    )
                except Exception as exc:
                    _append_writeback_record_failure(
                        failures,
                        reason="memory_writeback_record_invalid",
                        task_id=task_id,
                        record_id=str(outcome.get("memory_id") or ""),
                        error=exc,
                    )
            if written_back_to_learning:
                try:
                    learning_verified = _verify_learning_writeback_record(
                        learning_service,
                        task_id,
                        outcome.get("learning_trace_id"),
                    )
                except Exception as exc:
                    _append_writeback_record_failure(
                        failures,
                        reason="learning_writeback_record_invalid",
                        task_id=task_id,
                        record_id=str(outcome.get("learning_trace_id") or ""),
                        error=exc,
                    )

        receipts.append(
            {
                "task_id": task_id,
                "title": title,
                "q8_trace_id": trace_id,
                "q9_trace_id": q9_trace_id,
                "priority": str(getattr(_task_value(task, "priority"), "value", _task_value(task, "priority")) or ""),
                "outcome_passed": outcome.get("overall_passed") is True,
                "actual_outcome": actual_outcome,
                "writebacks": {
                    "reflection": {
                        "written": written_back_to_reflection,
                        "id": outcome.get("reflection_id"),
                        "verified": reflection_verified,
                    },
                    "memory": {
                        "written": written_back_to_memory,
                        "id": outcome.get("memory_id"),
                        "verified": memory_verified,
                    },
                    "learning": {
                        "written": written_back_to_learning,
                        "trace_id": outcome.get("learning_trace_id"),
                        "verified": learning_verified,
                    },
                },
            }
        )

    if failures:
        raise Q8ReplayIntegrityError(failures)

    return {
        "integrity_status": "passed",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "checked_task_count": len(tasks),
        "checked_outcome_count": len(receipts),
        "unique_q8_trace_count": len(seen_trace_ids),
        "require_writebacks": require_writebacks,
        "writeback_counts": writeback_counts,
        "receipts": receipts,
    }
