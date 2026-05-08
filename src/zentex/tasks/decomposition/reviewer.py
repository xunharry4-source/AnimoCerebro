from __future__ import annotations

import re
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
    _STRONG_VERIFICATION_TOKENS = (
        "hash",
        "mtime",
        "read-after-write",
        "read after write",
        "exit_code",
        "stdout",
        "stderr",
        "sqlite",
        "select",
        "query",
        "readback",
        "checksum",
        "diff",
        "sha",
        "写后查询",
        "读回",
        "回查",
        "数据库",
        "退出码",
        "执行输出",
        "文件",
        "标记文件",
        "修改时间",
        "哈希",
        "行数",
        "记录",
        "回执",
        "审计",
    )
    _WEAK_VERIFICATION_PATTERNS = (
        r"观察.*成功",
        r"等待.*执行完毕",
        r"是否成功",
        r"返回\s*success",
        r"返回.*成功",
        r"检查.*success",
        r"确认.*成功$",
        r"http\s*200$",
        r"\b200\s*ok$",
    )
    _WEAK_RESOURCE_PATTERNS = (
        r"^executor$",
        r"^tool$",
        r"^resource$",
        r"^执行方$",
        r"^工具$",
        r"^资源$",
        r"^appropriate\s+(executor|tool|resource)s?$",
        r"^suitable\s+(executor|tool|resource)s?$",
        r"^合适的\s*(执行方|工具|资源)$",
        r"^适当的\s*(执行方|工具|资源)$",
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
            required_resources = [str(resource or "").strip() for resource in list(getattr(item, "required_resources", []) or []) if str(resource or "").strip()]
            depends_on = [str(dep or "").strip() for dep in list(getattr(item, "depends_on", []) or [])]
            retry_count = int(getattr(item, "retry_count", 0) or 0)
            retry_budget = int(getattr(item, "retry_budget", 3) or 3)

            if not local_id:
                findings.append(AtomicSubtaskReviewFinding("missing_local_id", "subtask local_id is required", local_id))
            if not criteria:
                findings.append(AtomicSubtaskReviewFinding("missing_acceptance_criteria", "subtask must include acceptance criteria", local_id))
            if not required_resources:
                findings.append(AtomicSubtaskReviewFinding("missing_required_resources", "subtask must include at least one concrete required resource", local_id))

            criteria_text = " ".join(criteria).lower()
            if criteria and not any(token in criteria_text for token in self._STRONG_VERIFICATION_TOKENS):
                findings.append(
                    AtomicSubtaskReviewFinding(
                        "weak_acceptance_criteria",
                        "subtask acceptance criteria must include objective physical evidence such as read-after-write, exit_code, stdout/stderr, hash, mtime, or database/query readback",
                        local_id,
                    )
                )
            weak_verification_hits = [pattern for pattern in self._WEAK_VERIFICATION_PATTERNS if re.search(pattern, criteria_text, re.IGNORECASE)]
            if weak_verification_hits:
                findings.append(
                    AtomicSubtaskReviewFinding(
                        "weak_acceptance_criteria",
                        f"subtask acceptance criteria use vague verification language: {weak_verification_hits}",
                        local_id,
                    )
                )

            resource_hits = [pattern for pattern in self._WEAK_RESOURCE_PATTERNS if any(re.search(pattern, resource, re.IGNORECASE) for resource in required_resources)]
            if resource_hits:
                findings.append(
                    AtomicSubtaskReviewFinding(
                        "fake_execution_party",
                        f"subtask required_resources contain vague executor placeholders: {resource_hits}",
                        local_id,
                    )
                )

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
