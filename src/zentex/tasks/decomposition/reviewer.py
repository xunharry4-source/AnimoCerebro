from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from zentex.tasks.models import TaskStatus


@dataclass(frozen=True)
class AtomicSubtaskReviewFinding:
    code: str
    message: str
    local_id: str = ""


@dataclass(frozen=True)
class AtomicSubtaskReviewReport:
    accepted: bool
    findings: list[AtomicSubtaskReviewFinding] = field(default_factory=list)

    def raise_if_rejected(self) -> None:
        if self.accepted:
            return
        detail = "; ".join(f"{item.code}:{item.local_id}:{item.message}" for item in self.findings)
        raise RuntimeError(f"PydanticAI atomic subtask review rejected output: {detail}")


class PydanticAIAtomicSubtaskReviewer:
    """
    G31A deterministic reviewer for PydanticAI-generated subtasks.

    This is the code-level first defense. It does not call an LLM and must reject
    malformed or non-atomic records before any physical task is created.
    """

    _MULTI_ACTION_MARKERS = (
        "然后",
        "并且",
        "同时",
        "以及",
        "再",
        "并 ",
        " and ",
        " then ",
        " & ",
    )

    _LEGAL_STATUS_TRANSITIONS = {
        TaskStatus.TODO.value: {TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value, TaskStatus.BLOCKED.value, TaskStatus.CANCELLED.value},
        TaskStatus.SPLIT_REQUIRED.value: {TaskStatus.ASSIGNMENT_PENDING.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value},
        TaskStatus.ASSIGNMENT_PENDING.value: {TaskStatus.QUEUED.value, TaskStatus.BLOCKED.value, TaskStatus.FAILED.value, TaskStatus.SUSPENDED.value, TaskStatus.CANCELLED.value},
        TaskStatus.QUEUED.value: {TaskStatus.IN_PROGRESS.value, TaskStatus.BLOCKED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value},
        TaskStatus.IN_PROGRESS.value: {TaskStatus.DONE.value, TaskStatus.BLOCKED.value, TaskStatus.FAILED.value, TaskStatus.SUSPENDED.value},
        TaskStatus.BLOCKED.value: {TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
        TaskStatus.SUSPENDED.value: {TaskStatus.QUEUED.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    }

    def review_generated_subtasks(self, subtasks: Sequence[object]) -> AtomicSubtaskReviewReport:
        findings: list[AtomicSubtaskReviewFinding] = []
        local_ids = [str(getattr(item, "local_id", "") or "").strip() for item in subtasks]
        if len(local_ids) != len(set(local_ids)):
            findings.append(AtomicSubtaskReviewFinding("idempotency_collision", "duplicate local_id values in generated subtasks"))

        seen: set[str] = set()
        for item in subtasks:
            local_id = str(getattr(item, "local_id", "") or "").strip()
            title = str(getattr(item, "title", "") or "")
            content = str(getattr(item, "content", "") or "")
            criteria = list(getattr(item, "acceptance_criteria", []) or [])
            depends_on = [str(dep or "").strip() for dep in list(getattr(item, "depends_on", []) or [])]
            retry_count = int(getattr(item, "retry_count", 0) or 0)
            retry_budget = int(getattr(item, "retry_budget", 3) or 3)

            if not local_id:
                findings.append(AtomicSubtaskReviewFinding("missing_local_id", "subtask local_id is required", local_id))
            if not criteria:
                findings.append(AtomicSubtaskReviewFinding("missing_acceptance_criteria", "subtask must include acceptance criteria", local_id))

            multi_action_hits = [marker for marker in self._MULTI_ACTION_MARKERS if marker in f" {title} {content} ".lower()]
            if multi_action_hits:
                findings.append(
                    AtomicSubtaskReviewFinding(
                        "not_minimum_granularity",
                        f"subtask appears to contain multiple actions: {multi_action_hits}",
                        local_id,
                    )
                )

            unknown = [dep for dep in depends_on if dep not in local_ids]
            if unknown:
                findings.append(AtomicSubtaskReviewFinding("unknown_dependency", f"depends_on references unknown local_id: {unknown}", local_id))
            forward = [dep for dep in depends_on if dep not in seen]
            if forward:
                findings.append(AtomicSubtaskReviewFinding("dependency_loop", f"dependency points forward or forms a loop: {forward}", local_id))
            if retry_count >= retry_budget:
                findings.append(AtomicSubtaskReviewFinding("retry_budget_exhausted", "retry budget exhausted before task creation", local_id))
            seen.add(local_id)

        return AtomicSubtaskReviewReport(accepted=not findings, findings=findings)

    def review_status_transition(self, current_status: str, next_status: str, *, local_id: str = "") -> AtomicSubtaskReviewReport:
        allowed = self._LEGAL_STATUS_TRANSITIONS.get(str(current_status), set())
        if str(next_status) in allowed:
            return AtomicSubtaskReviewReport(accepted=True)
        return AtomicSubtaskReviewReport(
            accepted=False,
            findings=[
                AtomicSubtaskReviewFinding(
                    "illegal_status_transition",
                    f"{current_status} -> {next_status} is not allowed",
                    local_id,
                )
            ],
        )

    def review_physical_task_records(self, tasks: Iterable[Mapping[str, object]]) -> AtomicSubtaskReviewReport:
        findings: list[AtomicSubtaskReviewFinding] = []
        for task in tasks:
            local_id = str(task.get("task_id") or task.get("local_id") or "")
            metadata = task.get("metadata") if isinstance(task.get("metadata"), Mapping) else {}
            status = str(task.get("status") or "")
            owner_ref = str(metadata.get("owner_ref") or task.get("target_id") or "")
            dispatch_source = str(metadata.get("subtask_scheduled_by") or metadata.get("source") or "")
            attempt_count = int(task.get("attempt_count") or 0)
            retry_budget = int(metadata.get("retry_budget") or 3)

            if status in {TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value} and not owner_ref:
                findings.append(AtomicSubtaskReviewFinding("orphan_task", "dispatchable task has no owner_ref/target_id", local_id))
            if status in {TaskStatus.QUEUED.value, TaskStatus.IN_PROGRESS.value} and not dispatch_source:
                findings.append(AtomicSubtaskReviewFinding("stale_task", "dispatchable task has no scheduler/source marker", local_id))
            if attempt_count >= retry_budget:
                findings.append(AtomicSubtaskReviewFinding("retry_budget_exhausted", "physical task retry budget exhausted", local_id))
        return AtomicSubtaskReviewReport(accepted=not findings, findings=findings)
