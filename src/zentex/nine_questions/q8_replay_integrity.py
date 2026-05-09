from __future__ import annotations

from typing import Any

from zentex.audit.causal_chain import build_causal_audit_chain_report

TERMINAL_TASK_STATUSES = {"done", "failed", "blocked", "waiting_confirmation", "suspended", "archived"}


class Q8ReplayIntegrityError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 replay integrity check failed")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip()


def _task_status_history(task_service: Any, task_id: str) -> list[dict[str, Any]]:
    audit_dao = getattr(task_service, "_audit_dao", None)
    get_audit_history = getattr(audit_dao, "get_audit_history", None)
    if not callable(get_audit_history):
        return []
    rows = list(get_audit_history(task_id, limit=200) or [])
    transitions: list[dict[str, Any]] = []
    for row in reversed(rows):
        if not isinstance(row, dict) or row.get("action") != "TASK_STATUS_UPDATED":
            continue
        from_status = str(row.get("old_status") or row.get("from_status") or "").strip()
        to_status = str(row.get("new_status") or row.get("to_status") or "").strip()
        transitions.append(
            {
                "from_status": from_status,
                "to_status": to_status,
                "reason": row.get("details") or "",
                "audit_id": row.get("audit_id") or row.get("id") or "",
                "timestamp": row.get("timestamp") or "",
            }
        )
    return transitions


def _verify_terminal_status_history(
    task_service: Any,
    task_id: str,
    final_status: str,
) -> dict[str, Any]:
    history = _task_status_history(task_service, task_id)
    if final_status not in TERMINAL_TASK_STATUSES:
        return {"required": False, "final_status": final_status, "transitions": history}
    if not history:
        raise LookupError(f"terminal task {task_id} has no status transition audit history")

    missing_fields = [
        index
        for index, transition in enumerate(history)
        if not transition.get("from_status") or not transition.get("to_status")
    ]
    if missing_fields:
        raise LookupError(f"terminal task {task_id} has status transition audit rows missing from_status/to_status: {missing_fields}")

    terminal_indexes = [
        index
        for index, transition in enumerate(history)
        if transition.get("to_status") == final_status
    ]
    if not terminal_indexes:
        raise LookupError(f"terminal task {task_id} is missing a status transition audit to {final_status}")

    continuity_breaks: list[dict[str, Any]] = []
    previous = None
    for index, transition in enumerate(history):
        if previous is not None and previous.get("to_status") != transition.get("from_status"):
            continuity_breaks.append(
                {
                    "index": index,
                    "previous_to_status": previous.get("to_status"),
                    "current_from_status": transition.get("from_status"),
                }
            )
        previous = transition
    if continuity_breaks:
        raise LookupError(f"terminal task {task_id} has non-contiguous status transition audit history: {continuity_breaks}")

    return {
        "required": True,
        "verified": True,
        "final_status": final_status,
        "transition_count": len(history),
        "terminal_transition_index": terminal_indexes[-1],
        "transitions": history,
    }


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


def _verify_learning_evolution_record(learning_service: Any, task_id: str, learning_trace_id: Any) -> dict[str, Any]:
    learning_trace_id = str(learning_trace_id or "").strip()
    if not learning_trace_id:
        raise LookupError("learning_trace_id is empty")
    if learning_service is None or not callable(getattr(learning_service, "query_overall_records", None)):
        raise RuntimeError("learning_service.query_overall_records is required")
    records = list(learning_service.query_overall_records(limit=20, trace_id=learning_trace_id) or [])
    for record in records:
        detail = _as_dict(getattr(record, "detail", None))
        if detail.get("task_id") != task_id:
            continue
        if not detail.get("best_practice"):
            raise LookupError(f"learning record {learning_trace_id} is missing best_practice")
        if not detail.get("avoid_pattern"):
            raise LookupError(f"learning record {learning_trace_id} is missing avoid_pattern")
        if not detail.get("source_trace_id"):
            raise LookupError(f"learning record {learning_trace_id} is missing source_trace_id")
        if "actual_outcome" not in detail:
            raise LookupError(f"learning record {learning_trace_id} is missing actual_outcome")
        return {
            "verified": True,
            "learning_trace_id": learning_trace_id,
            "best_practice": detail.get("best_practice"),
            "avoid_pattern": detail.get("avoid_pattern"),
            "source_trace_id": detail.get("source_trace_id"),
            "evidence_ref": f"learning:{learning_trace_id}",
        }
    raise LookupError(f"learning record {learning_trace_id} does not belong to task {task_id}")


def _verify_reflection_evolution_record(reflection_service: Any, task_id: str, reflection_id: Any) -> dict[str, Any]:
    reflection_id = str(reflection_id or "").strip()
    if not reflection_id:
        raise LookupError("reflection_id is empty")
    if reflection_service is None or not callable(getattr(reflection_service, "get_reflection", None)):
        raise RuntimeError("reflection_service.get_reflection is required")
    reflection = reflection_service.get_reflection(reflection_id)
    context = _as_dict(getattr(reflection, "context", None))
    if context.get("task_id") != task_id:
        raise LookupError(f"reflection record {reflection_id} does not belong to task {task_id}")
    if not context.get("actionable_adjustment"):
        raise LookupError(f"reflection record {reflection_id} is missing actionable_adjustment")
    if not context.get("root_cause"):
        raise LookupError(f"reflection record {reflection_id} is missing root_cause")
    if "actual_outcome" not in context:
        raise LookupError(f"reflection record {reflection_id} is missing actual_outcome")
    return {
        "verified": True,
        "reflection_id": reflection_id,
        "root_cause": context.get("root_cause"),
        "actionable_adjustment": context.get("actionable_adjustment"),
        "evidence_ref": f"reflection:{reflection_id}",
    }


def _monitoring_recommendations(*, session_id: str, checked_task_count: int) -> list[dict[str, Any]]:
    return [
        {
            "monitor": "orphan_task_outcomes",
            "reason": "completed Q8 tasks must keep a resolvable TaskOutcome with matching trace_id",
            "scope": {"session_id": session_id, "checked_task_count": checked_task_count},
            "repair_hint": "backfill missing outcomes from task status history before accepting replay",
        },
        {
            "monitor": "writeback_link_integrity",
            "reason": "memory, learning, and reflection records must remain queryable from outcome ids",
            "scope": {"session_id": session_id, "checked_task_count": checked_task_count},
            "repair_hint": "rebuild writeback records or restore persisted ids before maintenance compaction",
        },
        {
            "monitor": "evolution_field_drift",
            "reason": "Learning best_practice/avoid_pattern and Reflection actionable_adjustment are replay-critical",
            "scope": {"session_id": session_id, "checked_task_count": checked_task_count},
            "repair_hint": "fail evolution replay when these fields are absent or lose task_id/trace provenance",
        },
    ]


def build_q8_replay_integrity_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    require_writebacks: bool = False,
    reflection_service: Any = None,
    memory_service: Any = None,
    learning_service: Any = None,
    audit_service: Any = None,
    required_audit_events: list[str | dict[str, Any]] | None = None,
    require_causal_chain: bool = False,
    require_evolution: bool = False,
    require_monitoring_recommendations: bool = True,
    require_status_history: bool = False,
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
    audit_chain_reports: list[dict[str, Any]] = []
    evolution_receipts: list[dict[str, Any]] = []
    writeback_counts = {
        "reflection": 0,
        "memory": 0,
        "learning": 0,
    }
    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        title = str(_task_value(task, "title") or "")
        task_status = _status_value(_task_value(task, "status"))
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

        status_history: dict[str, Any] = {"required": require_status_history, "final_status": task_status}
        if require_status_history:
            try:
                status_history = _verify_terminal_status_history(task_service, task_id, task_status)
            except Exception as exc:
                failures.append(
                    {
                        "reason": "terminal_status_history_invalid",
                        "task_id": task_id,
                        "final_status": task_status,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

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

        learning_evolution: dict[str, Any] = {"verified": False}
        reflection_evolution: dict[str, Any] = {"verified": False}
        if require_evolution:
            try:
                learning_evolution = _verify_learning_evolution_record(
                    learning_service,
                    task_id,
                    outcome.get("learning_trace_id"),
                )
            except Exception as exc:
                _append_writeback_record_failure(
                    failures,
                    reason="learning_evolution_record_invalid",
                    task_id=task_id,
                    record_id=str(outcome.get("learning_trace_id") or ""),
                    error=exc,
                )
            try:
                reflection_evolution = _verify_reflection_evolution_record(
                    reflection_service,
                    task_id,
                    outcome.get("reflection_id"),
                )
            except Exception as exc:
                _append_writeback_record_failure(
                    failures,
                    reason="reflection_evolution_record_invalid",
                    task_id=task_id,
                    record_id=str(outcome.get("reflection_id") or ""),
                    error=exc,
                )
            evolution_receipts.append(
                {
                    "task_id": task_id,
                    "learning": learning_evolution,
                    "reflection": reflection_evolution,
                    "evidence_refs": [
                        ref
                        for ref in (
                            learning_evolution.get("evidence_ref"),
                            reflection_evolution.get("evidence_ref"),
                        )
                        if ref
                    ],
                }
            )

        receipts.append(
            {
                "task_id": task_id,
                "title": title,
                "q8_trace_id": trace_id,
                "q9_trace_id": q9_trace_id,
                "priority": str(getattr(_task_value(task, "priority"), "value", _task_value(task, "priority")) or ""),
                "status": task_status,
                "status_history": status_history,
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
                "evolution": {
                    "required": require_evolution,
                    "learning_verified": learning_evolution.get("verified") is True,
                    "reflection_verified": reflection_evolution.get("verified") is True,
                },
            }
        )

    if require_causal_chain or required_audit_events:
        if audit_service is None:
            failures.append(
                {
                    "reason": "audit_service_missing",
                    "error_code": "WORKFLOW_AUDIT_SERVICE_MISSING",
                    "session_id": session_id,
                }
            )
        else:
            task_by_trace = {
                str(_as_dict(_task_value(task, "metadata")).get("trace_id") or ""): str(_task_value(task, "task_id") or "")
                for task in tasks
            }
            default_required_events: list[str | dict[str, Any]] = [
                "external_invoked",
                "node_succeeded",
                "writeback_verified",
            ]
            for trace_id in sorted(seen_trace_ids):
                try:
                    report = build_causal_audit_chain_report(
                        audit_service=audit_service,
                        trace_id=trace_id,
                        session_id=session_id,
                        task_id=task_by_trace.get(trace_id, ""),
                        required_audit_events=list(required_audit_events or default_required_events),
                    )
                except Exception as exc:
                    report = {
                        "status": "failed",
                        "error_code": "CAUSAL_AUDIT_BREAK",
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "task_id": task_by_trace.get(trace_id, ""),
                        "failures": [
                            {
                                "reason": "causal_audit_reader_failed",
                                "error_code": "CAUSAL_AUDIT_BREAK",
                                "trace_id": trace_id,
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                            }
                        ],
                    }
                audit_chain_reports.append(report)
                if report.get("status") != "succeeded":
                    for failure in report.get("failures") or []:
                        normalized_failure = dict(failure)
                        normalized_failure.setdefault("reason", "causal_audit_break")
                        normalized_failure.setdefault("status", "failed")
                        normalized_failure.setdefault("error_code", "CAUSAL_AUDIT_BREAK")
                        failures.append(normalized_failure)

    if failures:
        raise Q8ReplayIntegrityError(failures)

    recommendations = (
        _monitoring_recommendations(session_id=session_id, checked_task_count=len(tasks))
        if require_monitoring_recommendations
        else []
    )
    return {
        "integrity_status": "passed",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "checked_task_count": len(tasks),
        "checked_outcome_count": len(receipts),
        "unique_q8_trace_count": len(seen_trace_ids),
        "require_writebacks": require_writebacks,
        "writeback_counts": writeback_counts,
        "evolution_status": "passed" if require_evolution else "not_checked",
        "evolution_receipts": evolution_receipts,
        "audit_chain_status": "passed" if audit_chain_reports else "not_checked",
        "audit_chain_reports": audit_chain_reports,
        "monitoring_recommendations": recommendations,
        "receipts": receipts,
    }
