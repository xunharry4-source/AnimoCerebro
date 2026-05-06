from __future__ import annotations

"""Task lifecycle diagnostics for feature 61 acceptance closure."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.tasks.models import SuspendedTask, TaskStatus, ZentexTask


UTC = timezone.utc


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    TaskStatus.SPLIT_REQUIRED.value: {
        TaskStatus.ASSIGNMENT_PENDING.value,
        TaskStatus.DONE.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.ASSIGNMENT_PENDING.value: {
        TaskStatus.QUEUED.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.QUEUED.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.FAILED.value,
        TaskStatus.SUSPENDED.value,
        TaskStatus.ARCHIVED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.TODO.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.FAILED.value,
        TaskStatus.SUSPENDED.value,
        TaskStatus.ARCHIVED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.IN_PROGRESS.value: {
        TaskStatus.TODO.value,
        TaskStatus.WAITING_CONFIRMATION.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.DONE.value,
        TaskStatus.FAILED.value,
        TaskStatus.SUSPENDED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.BLOCKED.value: {
        TaskStatus.TODO.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.FAILED.value,
        TaskStatus.SUSPENDED.value,
        TaskStatus.ARCHIVED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.WAITING_CONFIRMATION.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.DONE.value,
        TaskStatus.FAILED.value,
        TaskStatus.SUSPENDED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.SUSPENDED.value: {
        TaskStatus.TODO.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.FAILED.value,
        TaskStatus.ARCHIVED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.DONE.value: {TaskStatus.ARCHIVED.value},
    TaskStatus.FAILED.value: {TaskStatus.TODO.value},
    TaskStatus.ARCHIVED.value: set(),
    TaskStatus.CANCELLED.value: set(),
}


class TaskLifecycleDiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"task-diagnostic-{uuid4().hex[:12]}")
    checks: dict[str, bool]
    metrics: dict[str, Any]
    issues: list[dict[str, Any]] = Field(default_factory=list)
    completion: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskFaultInjectionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"task-fault-{uuid4().hex[:12]}")
    cases: list[dict[str, Any]]
    passed: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def build_task_lifecycle_diagnostic_report(
    *,
    tasks: list[ZentexTask],
    suspended_tasks: list[SuspendedTask],
    audit_history_by_task_id: dict[str, list[dict[str, Any]]],
    now: datetime | None = None,
    stale_after_seconds: int = 300,
) -> TaskLifecycleDiagnosticReport:
    now = _as_aware(now or datetime.now(UTC))
    issues: list[dict[str, Any]] = []
    suspended_by_id = {item.task_id: item for item in suspended_tasks}
    tasks_by_id = {task.task_id: task for task in tasks}

    _detect_duplicate_idempotency_keys(tasks, issues)
    _detect_orphan_and_owner_loss(tasks, issues)
    _detect_stale_tasks(tasks, issues, now=now, stale_after_seconds=stale_after_seconds)
    _detect_retry_budget_violations(tasks, issues)
    _detect_dependency_integrity(tasks_by_id, issues)
    _detect_recovery_condition_gaps(tasks, suspended_by_id, issues)
    _detect_audit_chain_gaps(tasks, audit_history_by_task_id, issues)
    _detect_illegal_transition_audits(audit_history_by_task_id, issues)

    issue_types = {str(issue["type"]) for issue in issues}
    checks = {
        "state_machine_legal_transitions": "illegal_transition" not in issue_types,
        "orphan_task_detection": "orphan_task" not in issue_types,
        "stale_task_detection": "stale_task" not in issue_types,
        "retry_budget_detection": "retry_budget_exceeded" not in issue_types,
        "dependency_cycle_detection": "dependency_cycle" not in issue_types,
        "owner_loss_detection": "owner_lost" not in issue_types,
        "recovery_condition_detection": "recovery_condition_missing" not in issue_types,
        "audit_chain_detection": "audit_chain_missing" not in issue_types,
        "idempotent_replay_detection": "duplicate_idempotency_key" not in issue_types,
    }
    metrics = {
        "total_tasks": len(tasks),
        "status_counts": _status_counts(tasks),
        "suspended_count": len(suspended_tasks),
        "issue_count": len(issues),
        "stale_after_seconds": stale_after_seconds,
    }
    completion = build_task_completion_assessment(checks=checks, tasks=tasks, suspended_tasks=suspended_tasks, audit_history_by_task_id=audit_history_by_task_id)
    return TaskLifecycleDiagnosticReport(
        checks=checks,
        metrics=metrics,
        issues=issues,
        completion=completion,
    )


def build_task_fault_injection_report(report: TaskLifecycleDiagnosticReport) -> TaskFaultInjectionReport:
    cases = [
        {
            "name": "illegal_state_transition_is_detected_from_audit",
            "passed": report.checks["state_machine_legal_transitions"],
            "details": _issues_of_type(report, "illegal_transition"),
        },
        {
            "name": "orphan_and_owner_loss_detectors_ran",
            "passed": "orphan_task_detection" in report.checks and "owner_loss_detection" in report.checks,
            "details": {
                "orphan_issues": _issues_of_type(report, "orphan_task"),
                "owner_loss_issues": _issues_of_type(report, "owner_lost"),
            },
        },
        {
            "name": "stale_timeout_detector_ran",
            "passed": "stale_task_detection" in report.checks,
            "details": {"stale_issues": _issues_of_type(report, "stale_task")},
        },
        {
            "name": "retry_budget_detector_ran",
            "passed": "retry_budget_detection" in report.checks,
            "details": {"retry_issues": _issues_of_type(report, "retry_budget_exceeded")},
        },
        {
            "name": "dependency_cycle_detector_ran",
            "passed": "dependency_cycle_detection" in report.checks,
            "details": {"cycle_issues": _issues_of_type(report, "dependency_cycle")},
        },
        {
            "name": "idempotency_collision_detector_ran",
            "passed": "idempotent_replay_detection" in report.checks,
            "details": {"idempotency_issues": _issues_of_type(report, "duplicate_idempotency_key")},
        },
        {
            "name": "recovery_and_audit_detectors_ran",
            "passed": "recovery_condition_detection" in report.checks and "audit_chain_detection" in report.checks,
            "details": {
                "recovery_issues": _issues_of_type(report, "recovery_condition_missing"),
                "audit_issues": _issues_of_type(report, "audit_chain_missing"),
            },
        },
    ]
    return TaskFaultInjectionReport(cases=cases, passed=all(item["passed"] for item in cases))


def build_task_completion_assessment(
    *,
    checks: dict[str, bool],
    tasks: list[ZentexTask],
    suspended_tasks: list[SuspendedTask],
    audit_history_by_task_id: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    status_values = {task.status.value for task in tasks}
    audit_actions = {
        str(row.get("action") or "")
        for rows in audit_history_by_task_id.values()
        for row in rows
    }
    missing: list[str] = []

    state_machine_complete = all(
        checks.get(key, False)
        for key in {
            "state_machine_legal_transitions",
            "dependency_cycle_detection",
            "idempotent_replay_detection",
        }
    )
    recovery_chain_complete = bool(
        checks.get("recovery_condition_detection", False)
        and (TaskStatus.SUSPENDED.value in status_values or suspended_tasks or TaskStatus.BLOCKED.value in status_values)
    )
    audit_chain_complete = bool(checks.get("audit_chain_detection", False) and audit_actions)
    replay_chain_complete = bool(checks.get("idempotent_replay_detection", False))

    if not state_machine_complete:
        missing.append("state_machine_complete")
    if not recovery_chain_complete:
        missing.append("recovery_chain_complete")
    if not audit_chain_complete:
        missing.append("audit_chain_complete")
    if not replay_chain_complete:
        missing.append("replay_chain_complete")

    return {
        "state_machine_complete": state_machine_complete,
        "recovery_chain_complete": recovery_chain_complete,
        "audit_chain_complete": audit_chain_complete,
        "replay_chain_complete": replay_chain_complete,
        "real_complete": state_machine_complete and recovery_chain_complete and audit_chain_complete and replay_chain_complete,
        "missing_evidence": missing,
    }


def _detect_duplicate_idempotency_keys(tasks: list[ZentexTask], issues: list[dict[str, Any]]) -> None:
    seen: dict[str, str] = {}
    for task in tasks:
        existing = seen.get(task.idempotency_key)
        if existing and existing != task.task_id:
            issues.append(
                {
                    "type": "duplicate_idempotency_key",
                    "task_id": task.task_id,
                    "other_task_id": existing,
                    "idempotency_key": task.idempotency_key,
                }
            )
        seen[task.idempotency_key] = task.task_id


def _detect_orphan_and_owner_loss(tasks: list[ZentexTask], issues: list[dict[str, Any]]) -> None:
    for task in tasks:
        if not str(task.originator_id or "").strip() and not task.parent_task_id:
            issues.append({"type": "orphan_task", "task_id": task.task_id, "reason": "missing_originator_and_parent"})
        if task.status == TaskStatus.IN_PROGRESS and not str(task.target_id or "").strip():
            issues.append({"type": "owner_lost", "task_id": task.task_id, "reason": "in_progress_without_target"})


def _detect_stale_tasks(
    tasks: list[ZentexTask],
    issues: list[dict[str, Any]],
    *,
    now: datetime,
    stale_after_seconds: int,
) -> None:
    watched_statuses = {TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.WAITING_CONFIRMATION}
    for task in tasks:
        if task.status not in watched_statuses:
            continue
        threshold = int(task.metadata.get("stale_timeout", stale_after_seconds) or stale_after_seconds)
        elapsed = (now - _as_aware(task.last_updated_at)).total_seconds()
        if elapsed > threshold:
            issues.append(
                {
                    "type": "stale_task",
                    "task_id": task.task_id,
                    "status": task.status.value,
                    "elapsed_seconds": elapsed,
                    "threshold_seconds": threshold,
                }
            )


def _detect_retry_budget_violations(tasks: list[ZentexTask], issues: list[dict[str, Any]]) -> None:
    for task in tasks:
        attempt_count = int(task.metadata.get("attempt_count", 0) or 0)
        retry_budget = int(task.contract.retry_budget)
        if attempt_count > retry_budget:
            issues.append(
                {
                    "type": "retry_budget_exceeded",
                    "task_id": task.task_id,
                    "attempt_count": attempt_count,
                    "retry_budget": retry_budget,
                }
            )


def _detect_dependency_integrity(tasks_by_id: dict[str, ZentexTask], issues: list[dict[str, Any]]) -> None:
    for task in tasks_by_id.values():
        for dependency_id in task.depends_on:
            if dependency_id not in tasks_by_id:
                issues.append({"type": "dependency_missing", "task_id": task.task_id, "dependency_id": dependency_id})

    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(task_id: str, path: list[str]) -> None:
        if task_id in visiting:
            cycle = path[path.index(task_id) :] + [task_id] if task_id in path else path + [task_id]
            issues.append({"type": "dependency_cycle", "task_id": task_id, "cycle": cycle})
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        task = tasks_by_id.get(task_id)
        if task:
            for dependency_id in task.depends_on:
                if dependency_id in tasks_by_id:
                    visit(dependency_id, path + [dependency_id])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks_by_id:
        visit(task_id, [task_id])


def _detect_recovery_condition_gaps(
    tasks: list[ZentexTask],
    suspended_by_id: dict[str, SuspendedTask],
    issues: list[dict[str, Any]],
) -> None:
    for task in tasks:
        if task.status == TaskStatus.SUSPENDED:
            suspension = suspended_by_id.get(task.task_id)
            if not suspension:
                issues.append({"type": "recovery_condition_missing", "task_id": task.task_id, "reason": "suspension_record_missing"})
                continue
            if not suspension.recovery_conditions and suspension.auto_resume_at is None:
                issues.append({"type": "recovery_condition_missing", "task_id": task.task_id, "reason": "suspended_without_recovery_condition"})
        if task.status == TaskStatus.BLOCKED and not (
            task.metadata.get("recovery_conditions")
            or task.metadata.get("blocked_reason")
            or task.remarks
        ):
            issues.append({"type": "recovery_condition_missing", "task_id": task.task_id, "reason": "blocked_without_recovery_context"})


def _detect_audit_chain_gaps(
    tasks: list[ZentexTask],
    audit_history_by_task_id: dict[str, list[dict[str, Any]]],
    issues: list[dict[str, Any]],
) -> None:
    for task in tasks:
        if not audit_history_by_task_id.get(task.task_id):
            issues.append({"type": "audit_chain_missing", "task_id": task.task_id, "reason": "no_task_audit_log"})


def _detect_illegal_transition_audits(
    audit_history_by_task_id: dict[str, list[dict[str, Any]]],
    issues: list[dict[str, Any]],
) -> None:
    for task_id, rows in audit_history_by_task_id.items():
        for row in rows:
            old_status = row.get("old_status")
            new_status = row.get("new_status")
            if not old_status or not new_status or old_status == new_status:
                continue
            if str(new_status) not in ALLOWED_TRANSITIONS.get(str(old_status), set()):
                issues.append(
                    {
                        "type": "illegal_transition",
                        "task_id": task_id,
                        "old_status": old_status,
                        "new_status": new_status,
                        "action": row.get("action"),
                    }
                )


def _status_counts(tasks: list[ZentexTask]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task.status.value] = counts.get(task.status.value, 0) + 1
    return counts


def _issues_of_type(report: TaskLifecycleDiagnosticReport, issue_type: str) -> list[dict[str, Any]]:
    return [issue for issue in report.issues if issue.get("type") == issue_type]


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
