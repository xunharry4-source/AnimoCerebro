from __future__ import annotations

"""Automatic post-outcome writeback and maintenance orchestration."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(_as_dict(value) or value)


def _record_event(
    *,
    audit_service: Any,
    event_type: str,
    status: str,
    task_id: str,
    trace_id: str,
    session_id: str,
    output_summary: dict[str, Any],
    error_code: str = "",
) -> None:
    if audit_service is None:
        return
    from zentex.audit.workflow_events import record_workflow_node_event

    record_workflow_node_event(
        audit_service=audit_service,
        event_type=event_type,
        node_id="outcome-maintenance",
        node_name="Outcome writeback maintenance",
        status=status,
        trace_id=trace_id,
        session_id=session_id,
        task_id=task_id,
        output_summary=output_summary,
        error_code=error_code,
        evidence_ref=f"outcome_maintenance:{task_id}:{trace_id}",
        source="zentex.tasks.maintenance.outcome_maintenance",
    )


def _memory_record_payload(record: Any) -> dict[str, Any]:
    payload = getattr(record, "payload", None)
    if isinstance(payload, dict):
        return payload
    metadata = getattr(record, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _record_signature(record: Any) -> str:
    title = str(getattr(record, "title", "") or "").strip().lower()
    summary = str(getattr(record, "summary", "") or "").strip().lower()
    payload = _memory_record_payload(record)
    source = str(getattr(record, "source_kind", "") or payload.get("source") or "").strip().lower()
    return "|".join(part for part in (source, title, summary) if part)


def _analyze_maintenance_intelligence(memory_service: Any, *, task_id: str, trace_id: str) -> dict[str, Any]:
    records: list[Any] = []
    if memory_service is not None and callable(getattr(memory_service, "query_managed_records", None)):
        try:
            records = list(memory_service.query_managed_records(limit=250, status="active") or [])
        except TypeError:
            records = list(memory_service.query_managed_records(limit=250) or [])

    duplicate_groups: list[dict[str, Any]] = []
    groups: dict[str, list[Any]] = defaultdict(list)
    for record in records:
        signature = _record_signature(record)
        if signature:
            groups[signature].append(record)
    for signature, items in groups.items():
        if len(items) < 2:
            continue
        duplicate_groups.append(
            {
                "signature": signature,
                "count": len(items),
                "memory_ids": [str(getattr(item, "memory_id", "") or "") for item in items],
                "reason": "duplicate_or_mergeable_task_outcome_memory",
                "retention_policy": "merge summaries only after preserving task_id, trace_id, actual_outcome, and source outcome ids",
            }
        )

    low_value_candidates: list[dict[str, Any]] = []
    for record in records:
        payload = _memory_record_payload(record)
        missing = [
            name
            for name in ("task_id", "actual_outcome")
            if not (payload.get(name) or getattr(record, name, None))
        ]
        if missing and str(getattr(record, "source_kind", "") or payload.get("source") or "") == "task_outcome_writeback":
            low_value_candidates.append(
                {
                    "memory_id": str(getattr(record, "memory_id", "") or ""),
                    "missing_fields": missing,
                    "reason": "task_outcome_memory_missing_replay_fields",
                    "retention_policy": "do not delete before reconstructing replay fields",
                }
            )

    return {
        "task_id": task_id,
        "trace_id": trace_id,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_groups": duplicate_groups,
        "low_value_candidate_count": len(low_value_candidates),
        "low_value_candidates": low_value_candidates[:20],
        "compression_reasons": [
            "same source/title/summary indicates duplicate or mergeable task outcome memory",
            "low-value candidates are records missing replay-critical task_id, trace_id, or actual_outcome references",
        ],
        "retention_policy": "preserve task_id, trace_id, actual_outcome, overall_passed, and evidence_ref before any cleanup",
    }


async def run_automatic_outcome_maintenance(
    *,
    task_service: Any,
    task_id: str,
    memory_service: Any = None,
    learning_service: Any = None,
    reflection_service: Any = None,
    audit_service: Any = None,
    operator: str = "task_outcome_auto_hook",
) -> dict[str, Any]:
    outcome = task_service.get_task_outcome(task_id) if task_service is not None else None
    if not isinstance(outcome, dict):
        return {"status": "skipped", "reason": "task_outcome_missing", "task_id": task_id}

    task = task_service.get_task(task_id) if callable(getattr(task_service, "get_task", None)) else None
    metadata = getattr(task, "metadata", {}) if task is not None else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    trace_id = str(outcome.get("trace_id") or metadata.get("trace_id") or task_id)
    session_id = str(metadata.get("session_id") or getattr(task, "originator_id", "") or trace_id)
    original_overall_passed = outcome.get("overall_passed")
    started_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "status": "running",
        "trigger": "task_outcome_completed",
        "operator": operator,
        "task_id": task_id,
        "trace_id": trace_id,
        "session_id": session_id,
        "started_at": started_at,
        "original_overall_passed": original_overall_passed,
        "writebacks": {},
        "maintenance": {},
        "semantic_preservation": {
            "overall_passed_before": original_overall_passed,
            "failed_or_degraded_must_not_be_success": original_overall_passed is not True,
        },
    }
    _record_event(
        audit_service=audit_service,
        event_type="maintenance_started",
        status="running",
        task_id=task_id,
        trace_id=trace_id,
        session_id=session_id,
        output_summary={"trigger": report["trigger"], "original_overall_passed": original_overall_passed},
    )

    try:
        if original_overall_passed is True and memory_service is not None:
            report["writebacks"]["memory"] = task_service.write_task_outcome_to_memory(memory_service, task_id)
            _record_event(
                audit_service=audit_service,
                event_type="memory_writeback_finished",
                status="succeeded",
                task_id=task_id,
                trace_id=trace_id,
                session_id=session_id,
                output_summary={
                    "memory_id": report["writebacks"]["memory"].get("memory_id"),
                    "created": report["writebacks"]["memory"].get("created"),
                    "source": "automatic_outcome_maintenance",
                },
            )
        if learning_service is not None:
            report["writebacks"]["learning"] = task_service.write_task_outcome_to_learning(learning_service, task_id)
            _record_event(
                audit_service=audit_service,
                event_type="learning_writeback_finished",
                status="succeeded",
                task_id=task_id,
                trace_id=trace_id,
                session_id=session_id,
                output_summary={
                    "learning_trace_id": report["writebacks"]["learning"].get("learning_trace_id"),
                    "created": report["writebacks"]["learning"].get("created"),
                    "source": "automatic_outcome_maintenance",
                },
            )
        if reflection_service is not None:
            report["writebacks"]["reflection"] = task_service.write_task_outcome_to_reflection(reflection_service, task_id)
            _record_event(
                audit_service=audit_service,
                event_type="reflection_writeback_finished",
                status="succeeded",
                task_id=task_id,
                trace_id=trace_id,
                session_id=session_id,
                output_summary={
                    "reflection_id": report["writebacks"]["reflection"].get("reflection_id"),
                    "created": report["writebacks"]["reflection"].get("created"),
                    "source": "automatic_outcome_maintenance",
                },
            )

        if memory_service is not None and callable(getattr(memory_service, "trigger_automatic_consolidation_check", None)):
            result = memory_service.trigger_automatic_consolidation_check(force=True, operator=operator)
            report["maintenance"]["memory"] = _as_dict(result) or {"result": _text(result)}
        if learning_service is not None and callable(getattr(learning_service, "trigger_memory_aware_maintenance", None)):
            result = learning_service.trigger_memory_aware_maintenance(operator=operator, trigger="task_outcome_auto_hook", force=True)
            report["maintenance"]["learning"] = _as_dict(result) or {"result": _text(result)}
        if reflection_service is not None and callable(getattr(reflection_service, "trigger_memory_aware_maintenance", None)):
            result = reflection_service.trigger_memory_aware_maintenance(operator=operator, force=True)
            report["maintenance"]["reflection"] = _as_dict(result) or {"result": _text(result)}

        report["intelligence"] = _analyze_maintenance_intelligence(
            memory_service,
            task_id=task_id,
            trace_id=trace_id,
        )
        refreshed = task_service.get_task_outcome(task_id)
        report["semantic_preservation"]["overall_passed_after"] = refreshed.get("overall_passed") if isinstance(refreshed, dict) else None
        report["semantic_preservation"]["preserved"] = (
            report["semantic_preservation"]["overall_passed_after"] == original_overall_passed
        )
        report["status"] = "succeeded" if report["semantic_preservation"]["preserved"] else "failed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()

        if callable(getattr(task_service, "update_task_metadata", None)):
            await task_service.update_task_metadata(
                task_id,
                {"automatic_outcome_maintenance": report},
                remarks="Automatic outcome writeback maintenance completed",
            )
        _record_event(
            audit_service=audit_service,
            event_type="maintenance_finished",
            status=report["status"],
            task_id=task_id,
            trace_id=trace_id,
            session_id=session_id,
            output_summary={
                "status": report["status"],
                "fields_preserved": report["semantic_preservation"]["preserved"],
                "failed_or_degraded_must_not_be_success": report["semantic_preservation"][
                    "failed_or_degraded_must_not_be_success"
                ],
                "outcome_retained": bool(refreshed),
                "duplicate_group_count": report["intelligence"]["duplicate_group_count"],
                "low_value_candidate_count": report["intelligence"]["low_value_candidate_count"],
                "retention_policy": report["intelligence"]["retention_policy"],
            },
            error_code="" if report["status"] == "succeeded" else "OUTCOME_SEMANTIC_DRIFT",
        )
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _record_event(
            audit_service=audit_service,
            event_type="maintenance_finished",
            status="failed",
            task_id=task_id,
            trace_id=trace_id,
            session_id=session_id,
            output_summary={"status": "failed", "error": str(exc), "retention_policy": "preserve original outcome on maintenance failure"},
            error_code="OUTCOME_MAINTENANCE_FAILED",
        )
        if callable(getattr(task_service, "update_task_metadata", None)):
            await task_service.update_task_metadata(
                task_id,
                {"automatic_outcome_maintenance": report},
                remarks="Automatic outcome writeback maintenance failed",
            )
        return report
