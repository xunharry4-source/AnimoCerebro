from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from zentex.tasks.models import TaskScope, TaskStatus, TaskType


def _status_value(task: Any) -> str:
    status = getattr(task, "status", None)
    return str(getattr(status, "value", status) or "")


def _file_fingerprint(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _audit(
    *,
    audit_service: Any,
    event_type: str,
    node_id: str,
    node_name: str,
    status: str,
    trace_id: str,
    session_id: str,
    task_id: str = "",
    output_summary: dict[str, Any] | None = None,
    evidence_ref: str = "",
    error_code: str = "",
) -> dict[str, Any]:
    from zentex.audit.workflow_events import record_workflow_node_event

    return record_workflow_node_event(
        audit_service=audit_service,
        event_type=event_type,
        node_id=node_id,
        node_name=node_name,
        status=status,
        trace_id=trace_id,
        session_id=session_id,
        task_id=task_id,
        output_summary=output_summary or {},
        evidence_ref=evidence_ref,
        error_code=error_code,
        source="zentex.nine_questions.resource_recovery",
    )


def scan_resource_gaps(
    *,
    required_paths: list[Path],
    required_cli_tools: list[str],
    cli_service: Any,
    trace_id: str,
    session_id: str,
    audit_service: Any = None,
) -> dict[str, Any]:
    data_gaps: list[dict[str, Any]] = []
    data_sources: list[dict[str, Any]] = []
    for raw_path in required_paths:
        path = raw_path.expanduser()
        if not path.is_file():
            data_gaps.append({"gap_type": "DATA_GAP", "path": str(path), "reason": "required_file_missing"})
        else:
            data_sources.append(
                {
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "sha256": _file_fingerprint(path),
                }
            )

    capability_gaps: list[dict[str, Any]] = []
    healthy_capabilities: list[dict[str, Any]] = []
    for tool_name in required_cli_tools:
        health = cli_service.get_tool_health(tool_name) if cli_service is not None and callable(getattr(cli_service, "get_tool_health", None)) else {}
        if health.get("status") != "active" or health.get("healthy") is not True:
            capability_gaps.append(
                {
                    "gap_type": "CAPABILITY_GAP",
                    "tool": tool_name,
                    "reason": "cli_tool_unhealthy",
                    "health": health,
                }
            )
        else:
            healthy_capabilities.append({"tool": tool_name, "health": health})

    gaps = data_gaps + capability_gaps
    status = "blocked" if gaps else "succeeded"
    report = {
        "status": status,
        "trace_id": trace_id,
        "session_id": session_id,
        "data_gaps": data_gaps,
        "capability_gaps": capability_gaps,
        "data_sources": data_sources,
        "healthy_capabilities": healthy_capabilities,
        "missing_environment_sources": [gap["path"] for gap in data_gaps],
        "health_failed_capabilities": [gap["tool"] for gap in capability_gaps],
    }
    if audit_service is not None:
        _audit(
            audit_service=audit_service,
            event_type="question_output_checked",
            node_id="q1_gap_detect",
            node_name="Q1/Q3 Resource Gap Detection",
            status=status,
            trace_id=trace_id,
            session_id=session_id,
            output_summary=report,
            evidence_ref=f"resource_gap:{trace_id}",
            error_code="RESOURCE_GAP_DETECTED" if gaps else "",
        )
    return report


def build_recovery_plan_from_gaps(*, gap_report: dict[str, Any], trace_id: str, session_id: str, audit_service: Any = None) -> dict[str, Any]:
    gaps = list(gap_report.get("data_gaps") or []) + list(gap_report.get("capability_gaps") or [])
    recovery_tasks: list[dict[str, Any]] = []
    for index, gap in enumerate(gaps):
        if gap.get("gap_type") == "DATA_GAP":
            missing_path = str(gap.get("path") or "")
            recovery_tasks.append(
                {
                    "task_id": f"recover-data-gap-{index}",
                    "title": f"Request missing data file {Path(missing_path).name}",
                    "task_scope": TaskScope.INTERNAL.value,
                    "target_id": "internal:operator",
                    "metadata": {
                        "is_recovery_task": True,
                        "gap_type": "DATA_GAP",
                        "missing_path": missing_path,
                        "instructions_for_human": f"Provide a real file at {missing_path} or an equivalent approved data source.",
                    },
                }
            )
        elif gap.get("gap_type") == "CAPABILITY_GAP":
            tool = str(gap.get("tool") or "")
            recovery_tasks.append(
                {
                    "task_id": f"recover-capability-gap-{index}",
                    "title": f"Request credential or alternative for {tool}",
                    "task_scope": TaskScope.INTERNAL.value,
                    "target_id": "internal:operator",
                    "metadata": {
                        "is_recovery_task": True,
                        "gap_type": "CAPABILITY_GAP",
                        "tool": tool,
                        "instructions_for_human": f"Provide credential source for {tool} or approve a healthy fallback executor.",
                    },
                }
            )
    plan = {
        "status": "succeeded" if recovery_tasks else "failed",
        "trace_id": trace_id,
        "session_id": session_id,
        "recovery_tasks": recovery_tasks,
        "alternative_task_paths": ["resource_repair_then_retry"] if recovery_tasks else [],
    }
    if audit_service is not None:
        _audit(
            audit_service=audit_service,
            event_type="question_output_checked",
            node_id="q7_alt_find",
            node_name="Q7 Recovery Path Discovery",
            status=plan["status"],
            trace_id=trace_id,
            session_id=session_id,
            output_summary=plan,
            evidence_ref=f"resource_recovery_plan:{trace_id}",
        )
    return plan


async def request_human_resource_confirmation(
    *,
    task_service: Any,
    audit_service: Any,
    session_id: str,
    trace_id: str,
    recovery_task: dict[str, Any],
    recovery_target_task_id: str,
) -> Any:
    metadata = dict(recovery_task.get("metadata") or {})
    metadata.update(
        {
            "session_id": session_id,
            "trace_id": trace_id,
            "source": "resource_gap_recovery",
            "recovery_target_task_id": recovery_target_task_id,
        }
    )
    task = await task_service.create_task(
        {
            "idempotency_key": f"resource-recovery:{session_id}:{recovery_task.get('task_id')}",
            "title": str(recovery_task.get("title") or "Resource recovery request"),
            "task_type": TaskType.COGNITIVE_STEP,
            "task_scope": TaskScope.INTERNAL,
            "status": TaskStatus.WAITING_CONFIRMATION,
            "originator_id": session_id,
            "target_id": str(recovery_task.get("target_id") or "internal:operator"),
            "metadata": metadata,
        }
    )
    _audit(
        audit_service=audit_service,
        event_type="human_confirmation_requested",
        node_id="hitl_request",
        node_name="HITL Resource Request",
        status="waiting_confirmation",
        trace_id=trace_id,
        session_id=session_id,
        task_id=task.task_id,
        output_summary={
            "instructions_for_human": metadata.get("instructions_for_human"),
            "gap_type": metadata.get("gap_type"),
            "recovery_target_task_id": recovery_target_task_id,
        },
        evidence_ref=f"hitl_request:{task.task_id}",
    )
    return task


def record_human_resource_fix(
    *,
    audit_service: Any,
    trace_id: str,
    session_id: str,
    hitl_task_id: str,
    provided_paths: list[Path],
    approved_alternative: str = "",
) -> dict[str, Any]:
    path_evidence = []
    for raw_path in provided_paths:
        path = raw_path.expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Provided recovery path does not exist: {path}")
        path_evidence.append({"path": str(path), "size_bytes": path.stat().st_size, "sha256": _file_fingerprint(path)})
    payload = {
        "provided_path_evidence": path_evidence,
        "approved_alternative": approved_alternative,
        "secret_policy": "source_or_fingerprint_only",
    }
    _audit(
        audit_service=audit_service,
        event_type="human_confirmation_recorded",
        node_id="node_hitl_fix",
        node_name="Human Resource Fix",
        status="succeeded",
        trace_id=trace_id,
        session_id=session_id,
        task_id=hitl_task_id,
        output_summary=payload,
        evidence_ref=f"hitl_fix:{hitl_task_id}",
    )
    return payload


async def recover_resource_gap_tasks_after_recheck(
    *,
    task_service: Any,
    audit_service: Any,
    trace_id: str,
    session_id: str,
    blocked_task_ids: list[str],
    refreshed_gap_report: dict[str, Any],
    approved_alternative: str = "",
) -> dict[str, Any]:
    remaining_data_gaps = list(refreshed_gap_report.get("data_gaps") or [])
    remaining_capability_gaps = list(refreshed_gap_report.get("capability_gaps") or [])
    recoverable = not remaining_data_gaps and (not remaining_capability_gaps or bool(approved_alternative))
    resumed: list[dict[str, Any]] = []
    if recoverable:
        for task_id in blocked_task_ids:
            task = task_service.get_task(task_id)
            previous_status = _status_value(task)
            if previous_status not in {"blocked", "waiting_confirmation"}:
                continue
            updated = await task_service.update_task_status(
                task_id,
                TaskStatus.TODO,
                remarks="Resource gaps re-evaluated and recovered; task returned to queue.",
            )
            transition = {
                "task_id": task_id,
                "from_status": previous_status,
                "to_status": _status_value(updated),
                "reason": "resource_gap_recheck_passed",
            }
            resumed.append(transition)
            if callable(getattr(task_service, "update_task_metadata", None)):
                await task_service.update_task_metadata(
                    task_id,
                    {
                        "resource_gap_recovery_dispatch": {
                            "trace_id": trace_id,
                            "session_id": session_id,
                            "approved_alternative": approved_alternative,
                            "refreshed_gap_report": refreshed_gap_report,
                            "state_transition_history": [transition],
                        }
                    },
                    remarks="Resource gap recovery dispatch metadata recorded",
                )
    status = "succeeded" if recoverable else "blocked"
    report = {
        "status": status,
        "recoverable": recoverable,
        "remaining_data_gaps": remaining_data_gaps,
        "remaining_capability_gaps": remaining_capability_gaps,
        "approved_alternative": approved_alternative,
        "resumed_tasks": resumed,
    }
    _audit(
        audit_service=audit_service,
        event_type="posture_recovered" if recoverable else "node_blocked",
        node_id="re_eval_dispatch",
        node_name="Q9 Resource Recovery Dispatch",
        status=status,
        trace_id=trace_id,
        session_id=session_id,
        output_summary=report,
        evidence_ref=f"resource_recovery:{trace_id}",
        error_code="" if recoverable else "RESOURCE_GAP_STILL_PRESENT",
    )
    return report
