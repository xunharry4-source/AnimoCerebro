from __future__ import annotations

"""Deterministic task-center analysis for duplicate and noisy tasks."""

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.tasks.maintenance.garbage_analysis_prompt import (
    build_task_creation_noise_scoring_context,
    build_task_creation_noise_scoring_prompt,
)
from zentex.tasks.models import TaskScope, TaskStatus, ZentexTask


ACTIVE_STATUSES = {
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
    TaskStatus.BLOCKED,
    TaskStatus.WAITING_CONFIRMATION,
    TaskStatus.SUSPENDED,
}
WATCHED_STALE_STATUSES = {
    TaskStatus.IN_PROGRESS,
    TaskStatus.BLOCKED,
    TaskStatus.WAITING_CONFIRMATION,
}
GENERIC_TITLES = {
    "task",
    "todo",
    "pending task",
    "planned task",
    "generated task",
    "q8 generated task",
    "q9 generated task",
    "action item",
}


def build_task_garbage_analysis_report(
    *,
    tasks: list[ZentexTask],
    now: datetime | None = None,
    stale_after_seconds: int = 300,
    max_examples_per_group: int = 8,
    enable_llm_semantic_scoring: bool = False,
    llm_service: Any | None = None,
    max_llm_groups: int = 8,
) -> dict[str, Any]:
    """Build a read-only quality report for duplicates and noisy tasks."""
    now = _as_aware(now or datetime.now(timezone.utc))
    tasks_by_id = {task.task_id: task for task in tasks}
    dependency_deadlocked_task_ids = _dependency_deadlocked_task_ids(tasks_by_id)
    duplicate_groups = _detect_duplicate_groups(
        tasks,
        max_examples_per_group=max_examples_per_group,
    )
    garbage_candidates = _detect_garbage_candidates(
        tasks,
        tasks_by_id=tasks_by_id,
        dependency_deadlocked_task_ids=dependency_deadlocked_task_ids,
        now=now,
        stale_after_seconds=stale_after_seconds,
    )
    garbage_candidates.sort(key=_candidate_sort_key)
    llm_evaluations = _build_llm_semantic_evaluations(
        tasks_by_id=tasks_by_id,
        duplicate_groups=duplicate_groups,
        enable_llm_semantic_scoring=enable_llm_semantic_scoring,
        llm_service=llm_service,
        max_llm_groups=max_llm_groups,
    )
    task_assessments = _build_task_assessments(
        tasks_by_id=tasks_by_id,
        duplicate_groups=duplicate_groups,
        garbage_candidates=garbage_candidates,
        dependency_deadlocked_task_ids=dependency_deadlocked_task_ids,
        llm_evaluations=llm_evaluations,
    )
    active_count = sum(1 for task in tasks if task.status in ACTIVE_STATUSES)
    source_counts = Counter(_source_module(task) for task in tasks)
    q9_task_count = sum(1 for task in tasks if _source_module(task) == "nine_questions.q9")
    high_risk_count = sum(
        1
        for item in [*duplicate_groups, *garbage_candidates]
        if item["severity"] in {"critical", "high"}
    )
    return {
        "report_id": f"task-garbage-{uuid4().hex[:12]}",
        "generated_at": now.isoformat(),
        "stale_after_seconds": stale_after_seconds,
        "summary": {
            "total_tasks": len(tasks),
            "active_tasks": active_count,
            "q9_task_count": q9_task_count,
            "duplicate_group_count": len(duplicate_groups),
            "garbage_candidate_count": len(garbage_candidates),
            "high_risk_count": high_risk_count,
        },
        "source_counts": dict(sorted(source_counts.items())),
        "duplicate_groups": duplicate_groups,
        "garbage_candidates": garbage_candidates,
        "task_assessments": task_assessments,
        "llm_semantic_scoring": {
            "enabled": enable_llm_semantic_scoring,
            "mandatory_for_semantic_decisions": True,
            "evaluated_group_count": sum(
                1
                for item in llm_evaluations.values()
                if item.get("status") == "evaluated"
            ),
            "unavailable_group_count": sum(
                1
                for item in llm_evaluations.values()
                if item.get("status") == "llm_required_but_unavailable"
            ),
        },
        "execution_plan": {
            "auto_execution_enabled": False,
            "reason": "This endpoint is an auditable analysis surface; merge/drop/cancel actions require an explicit policy executor.",
            "candidate_action_count": sum(
                1
                for assessment in task_assessments
                if assessment["final_decision"] in {"merge_and_drop", "cancel_by_policy", "cancel_by_timeout", "cancel_by_conflict"}
            ),
        },
    }


def build_task_creation_analysis_report(
    *,
    existing_tasks: list[ZentexTask],
    candidate_task: ZentexTask,
    force_execute: bool = False,
    enable_llm_semantic_scoring: bool = False,
    llm_service: Any | None = None,
    workspace_environment_context: dict[str, Any] | None = None,
    duplicate_threshold: float = 0.85,
    junk_threshold: float = 0.85,
    max_comparison_tasks: int = 40,
) -> dict[str, Any]:
    """Score one candidate before it is admitted into the task center."""
    candidate_id = candidate_task.task_id
    report = build_task_garbage_analysis_report(
        tasks=[*existing_tasks, candidate_task],
        enable_llm_semantic_scoring=False,
    )
    assessment = next(
        (item for item in report["task_assessments"] if item["task_id"] == candidate_id),
        _base_assessment(candidate_task, dependency_deadlocked_task_ids=set()),
    )
    rule_scores = _candidate_rule_scores(assessment)
    llm_evaluation = _score_creation_candidate_with_llm(
        candidate_task=candidate_task,
        comparison_tasks=_comparison_tasks(existing_tasks, max_count=max_comparison_tasks),
        enable_llm_semantic_scoring=enable_llm_semantic_scoring,
        llm_service=llm_service,
        workspace_environment_context=workspace_environment_context,
    )
    duplicate_score = max(rule_scores["duplicate_score"], _score_or_none(llm_evaluation.get("duplicate_score")) or 0.0)
    junk_score = max(rule_scores["junk_score"], _score_or_none(llm_evaluation.get("junk_score")) or 0.0)
    target_merge_task_id = assessment.get("target_merge_task_id") or llm_evaluation.get("target_merge_task_id")
    rejection_reason = _creation_rejection_reason(
        candidate_task=candidate_task,
        assessment=assessment,
        llm_evaluation=llm_evaluation,
        duplicate_score=duplicate_score,
        junk_score=junk_score,
        target_merge_task_id=target_merge_task_id,
    )
    should_reject = (
        duplicate_score >= duplicate_threshold
        or junk_score >= junk_threshold
        or assessment.get("final_decision") in {"merge_and_drop", "cancel_by_policy", "cancel_by_timeout", "cancel_by_conflict"}
    )
    if force_execute and should_reject:
        decision = "force_allowed"
    elif should_reject:
        llm_decision = str(llm_evaluation.get("decision") or "")
        if llm_decision == "merge_and_drop" or assessment.get("final_decision") == "merge_and_drop" or target_merge_task_id:
            decision = "merge_and_drop"
        else:
            decision = "rejected"
    else:
        decision = "approved"
    return {
        "TaskAnalysisReport": {
            "task_id": candidate_id,
            "evaluation_mode": "hybrid_rule_and_llm" if enable_llm_semantic_scoring else "rule_based_with_llm_slot",
            "scores": {
                "duplicate_score": round(duplicate_score, 6),
                "junk_score": round(junk_score, 6),
            },
            "decision": decision,
            "rejection_reason": rejection_reason if should_reject else None,
            "force_execute_flag": force_execute,
            "target_merge_task_id": target_merge_task_id,
            "rule_based_flags": assessment.get("rule_based_flags", {}),
            "rule_based_decision": assessment.get("final_decision"),
            "llm_semantic_evaluation": llm_evaluation,
            "thresholds": {
                "duplicate_threshold": duplicate_threshold,
                "junk_threshold": junk_threshold,
            },
        }
    }


def _detect_duplicate_groups(
    tasks: list[ZentexTask],
    *,
    max_examples_per_group: int,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    _append_grouped_duplicates(
        groups,
        group_kind="idempotency_key",
        severity="critical",
        tasks_by_signature=_group_tasks(tasks, _idempotency_signature),
        reason="Multiple tasks share the same idempotency key; replay protection may have been bypassed.",
        recommended_action="Inspect persistence/idempotency writes and keep only the canonical task after review.",
        max_examples_per_group=max_examples_per_group,
    )
    active_tasks = [task for task in tasks if task.status in ACTIVE_STATUSES]
    _append_grouped_duplicates(
        groups,
        group_kind="semantic_signature",
        severity="high",
        tasks_by_signature=_group_tasks(active_tasks, _semantic_signature),
        reason="Active tasks have the same source, target, type, and normalized work description.",
        recommended_action="Merge or archive duplicates after confirming the canonical task.",
        max_examples_per_group=max_examples_per_group,
    )
    q9_tasks = [task for task in active_tasks if _source_module(task) == "nine_questions.q9"]
    _append_grouped_duplicates(
        groups,
        group_kind="q9_blueprint_step",
        severity="high",
        tasks_by_signature=_group_tasks(q9_tasks, _q9_step_signature),
        reason="Q9 generated repeated active blueprint steps across task parents or sessions.",
        recommended_action="Review Q9 task sync/decomposition input and archive superseded generated children.",
        max_examples_per_group=max_examples_per_group,
    )
    groups.sort(key=lambda item: ({"critical": 0, "high": 1, "medium": 2}.get(item["severity"], 9), item["group_kind"]))
    return groups


def _candidate_rule_scores(assessment: dict[str, Any]) -> dict[str, float]:
    flags = assessment.get("rule_based_flags", {})
    issue_types = set(assessment.get("garbage_issue_types") or [])
    duplicate_score = 1.0 if flags.get("is_idempotency_duplicate") else 0.0
    junk_score = 0.0
    if flags.get("is_dependency_deadlock") or flags.get("is_retry_budget_exhausted"):
        junk_score = 1.0
    elif flags.get("is_orphan_or_stale"):
        junk_score = 1.0
    elif "missing_executor_binding" in issue_types:
        junk_score = 0.9
    elif "missing_parent_task" in issue_types or "q9_generated_child_without_parent" in issue_types:
        junk_score = 0.9
    elif "low_information_task" in issue_types:
        junk_score = 0.75
    return {"duplicate_score": duplicate_score, "junk_score": junk_score}


def _score_creation_candidate_with_llm(
    *,
    candidate_task: ZentexTask,
    comparison_tasks: list[ZentexTask],
    enable_llm_semantic_scoring: bool,
    llm_service: Any | None,
    workspace_environment_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not enable_llm_semantic_scoring:
        return {
            "status": "not_requested",
            "duplicate_score": None,
            "junk_score": None,
            "evaluation_reason": "LLM semantic scoring was not requested for this creation gate.",
            "target_merge_task_id": None,
        }
    if llm_service is None:
        try:
            from zentex.llm import get_llm_service

            llm_service = get_llm_service()
        except Exception as exc:
            return _creation_llm_unavailable(exc)
    context = build_task_creation_noise_scoring_context(
        candidate_task=_task_llm_context(candidate_task),
        comparison_tasks=[_task_llm_context(task) for task in comparison_tasks],
        workspace_environment_context=workspace_environment_context,
    )
    prompt = build_task_creation_noise_scoring_prompt()
    try:
        result = llm_service.generate_json(
            prompt=prompt,
            context=context,
            source_module="zentex.tasks.creation_noise_gate",
            invocation_phase="task_creation_noise_scoring",
            temperature=0.0,
            max_output_tokens=1000,
            metadata={"llm_mandatory": True, "task_creation_noise_gate": True},
        )
        raw = getattr(result, "output", result)
        return _normalize_creation_llm_payload(raw)
    except Exception as exc:
        return _creation_llm_unavailable(exc)


def _creation_rejection_reason(
    *,
    candidate_task: ZentexTask,
    assessment: dict[str, Any],
    llm_evaluation: dict[str, Any],
    duplicate_score: float,
    junk_score: float,
    target_merge_task_id: Any,
) -> str:
    flags = assessment.get("rule_based_flags", {})
    issues = ", ".join(assessment.get("garbage_issue_types") or [])
    if flags.get("is_idempotency_duplicate"):
        return (
            f"拒绝理由：规则幂等判重命中 (duplicate_score: {duplicate_score:.2f})。"
            f"任务 `{candidate_task.title}` 与已存在任务共享 idempotency_key，目标合并任务为 {target_merge_task_id}。"
        )
    if flags.get("is_dependency_deadlock"):
        return "拒绝理由：规则检测到依赖环死锁，任务不能进入执行队列。"
    if flags.get("is_retry_budget_exhausted"):
        return "拒绝理由：规则检测到重试预算已耗尽，继续创建会形成僵尸/重试风暴。"
    if junk_score >= 0.85 and issues:
        return f"拒绝理由：规则噪音检测命中 (junk_score: {junk_score:.2f})，问题类型：{issues}。"
    if (llm_evaluation.get("duplicate_score") or 0) >= 0.85:
        return (
            f"拒绝理由：LLM 语义判重命中 (duplicate_score: {duplicate_score:.2f})。"
            f"{llm_evaluation.get('evaluation_reason') or '该任务与现有活跃/近期任务目标高度重合。'}"
        )
    if (llm_evaluation.get("junk_score") or 0) >= 0.85:
        return (
            f"拒绝理由：LLM 噪音判定命中 (junk_score: {junk_score:.2f})。"
            f"{llm_evaluation.get('evaluation_reason') or '该任务缺乏可执行价值或上下文依据。'}"
        )
    return "拒绝理由：任务噪音/重复策略命中，未进入执行队列。"


def _normalize_creation_llm_payload(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    report = payload.get("TaskAnalysisReport") if isinstance(payload.get("TaskAnalysisReport"), dict) else payload
    scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    rejection_reason = report.get("rejection_reason")
    if not rejection_reason or rejection_reason == "none":
        rejection_reason = report.get("evaluation_reason") or ""
    return {
        "status": "evaluated",
        "duplicate_score": _clamp_score(scores.get("duplicate_score", report.get("duplicate_score"))),
        "junk_score": _clamp_score(scores.get("junk_score", report.get("junk_score"))),
        "decision": str(report.get("decision") or "").strip() or None,
        "evaluation_reason": str(rejection_reason or "").strip()[:800],
        "target_merge_task_id": report.get("target_merge_task_id") or None,
        "raw_task_analysis_report": report if isinstance(report, dict) else {},
    }


def _comparison_tasks(tasks: list[ZentexTask], *, max_count: int) -> list[ZentexTask]:
    active_or_recent = [
        task
        for task in tasks
        if task.status in ACTIVE_STATUSES or task.status == TaskStatus.DONE
    ]
    active_or_recent.sort(key=lambda task: _as_aware(task.last_updated_at), reverse=True)
    return active_or_recent[: max(0, int(max_count))]


def _creation_llm_unavailable(exc: Exception) -> dict[str, Any]:
    return {
        "status": "llm_required_but_unavailable",
        "duplicate_score": None,
        "junk_score": None,
        "evaluation_reason": f"LLM semantic scoring is mandatory for semantic decisions but unavailable: {type(exc).__name__}: {exc}",
        "target_merge_task_id": None,
    }


def _append_grouped_duplicates(
    groups: list[dict[str, Any]],
    *,
    group_kind: str,
    severity: str,
    tasks_by_signature: dict[str, list[ZentexTask]],
    reason: str,
    recommended_action: str,
    max_examples_per_group: int,
) -> None:
    for signature, members in sorted(tasks_by_signature.items()):
        unique_members = _unique_tasks(members)
        if len(unique_members) < 2:
            continue
        examples = unique_members[:max_examples_per_group]
        groups.append(
            {
                "group_id": f"{group_kind}:{_stable_digest(signature)}",
                "group_kind": group_kind,
                "severity": severity,
                "signature": signature,
                "reason": reason,
                "recommended_action": recommended_action,
                "task_ids": [task.task_id for task in examples],
                "task_count": len(unique_members),
                "titles": [task.title for task in examples],
                "source_module": _source_module(unique_members[0]),
                "statuses": sorted({task.status.value for task in unique_members}),
            }
        )


def _build_llm_semantic_evaluations(
    *,
    tasks_by_id: dict[str, ZentexTask],
    duplicate_groups: list[dict[str, Any]],
    enable_llm_semantic_scoring: bool,
    llm_service: Any | None,
    max_llm_groups: int,
) -> dict[str, dict[str, Any]]:
    semantic_groups = [
        group
        for group in duplicate_groups
        if group["group_kind"] in {"semantic_signature", "q9_blueprint_step"}
    ][: max(0, int(max_llm_groups))]
    if not semantic_groups:
        return {}
    if not enable_llm_semantic_scoring:
        return {
            group["group_id"]: {
                "status": "not_requested",
                "semantic_duplicate_score": None,
                "garbage_noise_score": None,
                "comprehensive_value_score": None,
                "evaluation_reason": "LLM semantic scoring was not requested for this analysis run.",
                "target_merge_task_id": None,
            }
            for group in semantic_groups
        }
    if llm_service is None:
        try:
            from zentex.llm import get_llm_service

            llm_service = get_llm_service()
        except Exception as exc:
            return {
                group["group_id"]: _llm_unavailable_evaluation(exc)
                for group in semantic_groups
            }
    context = {
        "semantic_duplicate_groups": [
            {
                "group_id": group["group_id"],
                "group_kind": group["group_kind"],
                "reason": group["reason"],
                "tasks": [
                    _task_llm_context(tasks_by_id[task_id])
                    for task_id in group["task_ids"]
                    if task_id in tasks_by_id
                ],
            }
            for group in semantic_groups
        ],
        "decision_thresholds": {
            "merge_and_drop_semantic_duplicate_score": 0.8,
            "cancel_garbage_noise_score": 0.85,
        },
    }
    prompt = (
        "You are the Zentex Task Garbage & Duplication Analyzer. "
        "Score only semantic intent and task value; do not invent task IDs. "
        "Return strict JSON: {\"evaluations\":[{\"group_id\":\"...\","
        "\"semantic_duplicate_score\":0.0,\"garbage_noise_score\":0.0,"
        "\"comprehensive_value_score\":0.0,\"evaluation_reason\":\"short reason\","
        "\"target_merge_task_id\":\"task id or null\",\"final_decision\":\"allow|monitor|merge_and_drop|cancel_by_policy\"}]}."
    )
    try:
        result = llm_service.generate_json(
            prompt=prompt,
            context=context,
            source_module="zentex.tasks.garbage_analysis",
            invocation_phase="task_garbage_semantic_scoring",
            temperature=0.0,
            max_output_tokens=1800,
            metadata={"llm_mandatory": True, "semantic_task_garbage_analysis": True},
        )
        raw = getattr(result, "output", result)
        return _normalize_llm_evaluation_payload(raw, semantic_groups)
    except Exception as exc:
        return {
            group["group_id"]: _llm_unavailable_evaluation(exc)
            for group in semantic_groups
        }


def _build_task_assessments(
    *,
    tasks_by_id: dict[str, ZentexTask],
    duplicate_groups: list[dict[str, Any]],
    garbage_candidates: list[dict[str, Any]],
    dependency_deadlocked_task_ids: set[str],
    llm_evaluations: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    assessments_by_task_id: dict[str, dict[str, Any]] = {}
    garbage_by_task_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in garbage_candidates:
        garbage_by_task_id[str(candidate["task_id"])].append(candidate)

    for group in duplicate_groups:
        task_ids = [task_id for task_id in group["task_ids"] if task_id in tasks_by_id]
        if not task_ids:
            continue
        canonical_task_id = task_ids[0]
        llm_evaluation = llm_evaluations.get(group["group_id"])
        for index, task_id in enumerate(task_ids):
            task = tasks_by_id[task_id]
            assessment = assessments_by_task_id.setdefault(
                task_id,
                _base_assessment(task, dependency_deadlocked_task_ids=dependency_deadlocked_task_ids),
            )
            assessment["duplicate_group_ids"].append(group["group_id"])
            if group["group_kind"] == "idempotency_key" and index > 0:
                assessment["rule_based_flags"]["is_idempotency_duplicate"] = True
                assessment["rule_based_score"] = 1.0
                assessment["target_merge_task_id"] = canonical_task_id
                assessment["final_decision"] = "merge_and_drop"
            elif llm_evaluation:
                assessment["llm_semantic_evaluation"] = llm_evaluation
                semantic_score = _score_or_none(llm_evaluation.get("semantic_duplicate_score"))
                noise_score = _score_or_none(llm_evaluation.get("garbage_noise_score"))
                if semantic_score is not None and semantic_score >= 0.8 and index > 0:
                    assessment["target_merge_task_id"] = llm_evaluation.get("target_merge_task_id") or canonical_task_id
                    assessment["final_decision"] = "merge_and_drop"
                elif noise_score is not None and noise_score >= 0.85:
                    assessment["final_decision"] = "cancel_by_policy"
                elif assessment["final_decision"] == "allow":
                    assessment["final_decision"] = "monitor"

    for task_id, candidates in garbage_by_task_id.items():
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        assessment = assessments_by_task_id.setdefault(
            task_id,
            _base_assessment(task, dependency_deadlocked_task_ids=dependency_deadlocked_task_ids),
        )
        assessment["garbage_issue_types"] = sorted({str(item["issue_type"]) for item in candidates})
        if any(item["issue_type"] == "dependency_deadlock" for item in candidates):
            assessment["rule_based_flags"]["is_dependency_deadlock"] = True
            assessment["rule_based_score"] = 1.0
            assessment["final_decision"] = "cancel_by_conflict"
        elif any(item["issue_type"] in {"retry_budget_exhausted", "orphan_task"} for item in candidates):
            assessment["rule_based_flags"]["is_orphan_or_stale"] = True
            assessment["rule_based_score"] = max(float(assessment["rule_based_score"]), 1.0)
            assessment["final_decision"] = "cancel_by_policy"
        elif any(item["issue_type"] == "stale_active_task" for item in candidates):
            assessment["rule_based_flags"]["is_orphan_or_stale"] = True
            assessment["rule_based_score"] = max(float(assessment["rule_based_score"]), 1.0)
            assessment["final_decision"] = "cancel_by_timeout"
        elif assessment["final_decision"] == "allow":
            assessment["final_decision"] = "monitor"

    assessments = list(assessments_by_task_id.values())
    assessments.sort(key=lambda item: _assessment_sort_key(item))
    return assessments


def _detect_garbage_candidates(
    tasks: list[ZentexTask],
    *,
    tasks_by_id: dict[str, ZentexTask],
    dependency_deadlocked_task_ids: set[str],
    now: datetime,
    stale_after_seconds: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for task in tasks:
        metadata = _metadata(task)
        if task.task_id in dependency_deadlocked_task_ids:
            candidates.append(
                _candidate(
                    task,
                    severity="critical",
                    issue_type="dependency_deadlock",
                    reason="Task participates in a dependency cycle.",
                    recommended_action="Cancel or relink one edge in the cycle before dispatching physical execution.",
                )
            )
        if _retry_budget_exhausted(task):
            candidates.append(
                _candidate(
                    task,
                    severity="critical",
                    issue_type="retry_budget_exhausted",
                    reason="Retry attempts have exceeded the task contract retry budget.",
                    recommended_action="Stop automatic retries and mark the task as policy-cancelled or failed with evidence.",
                )
            )
        if task.status in WATCHED_STALE_STATUSES:
            threshold = int(metadata.get("stale_timeout", stale_after_seconds) or stale_after_seconds)
            elapsed = max(0, int((now - _as_aware(task.last_updated_at)).total_seconds()))
            if elapsed > threshold:
                candidates.append(
                    _candidate(
                        task,
                        severity="high" if task.status == TaskStatus.IN_PROGRESS else "medium",
                        issue_type="stale_active_task",
                        reason=f"No progress update for {elapsed} seconds, exceeding threshold {threshold}.",
                        recommended_action="Retry, fail, suspend, or archive after checking the latest execution evidence.",
                        age_seconds=elapsed,
                    )
                )
        if not str(task.originator_id or "").strip() and not task.parent_task_id:
            candidates.append(
                _candidate(
                    task,
                    severity="high",
                    issue_type="orphan_task",
                    reason="Task has no originator and no parent task.",
                    recommended_action="Assign an owner or archive after verifying it is not actionable.",
                )
            )
        if _is_low_information_task(task):
            candidates.append(
                _candidate(
                    task,
                    severity="medium",
                    issue_type="low_information_task",
                    reason="Title and description do not contain enough actionable detail.",
                    recommended_action="Regenerate with a concrete objective or archive as noise.",
                )
            )
        if (
            task.task_scope == TaskScope.EXTERNAL
            and task.status in {TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}
            and not str(task.target_id or task.dispatch_plugin_id or "").strip()
        ):
            candidates.append(
                _candidate(
                    task,
                    severity="medium",
                    issue_type="missing_executor_binding",
                    reason="External task has no target executor or dispatch plugin.",
                    recommended_action="Route through resource matching or archive if the action is no longer valid.",
                )
            )
        if task.parent_task_id and task.parent_task_id not in tasks_by_id:
            candidates.append(
                _candidate(
                    task,
                    severity="medium",
                    issue_type="missing_parent_task",
                    reason="Task references a parent task that is no longer present.",
                    recommended_action="Relink to the canonical parent or archive as an orphaned generated child.",
                )
            )
        if _source_module(task) == "nine_questions.q9" and _looks_generated_child_without_parent(task, tasks_by_id):
            candidates.append(
                _candidate(
                    task,
                    severity="high",
                    issue_type="q9_generated_child_without_parent",
                    reason="Q9 generated child lost its blueprint parent linkage.",
                    recommended_action="Inspect Q9 decomposition and archive the child if no canonical parent exists.",
                )
            )
    return _unique_candidates(candidates)


def _base_assessment(
    task: ZentexTask,
    *,
    dependency_deadlocked_task_ids: set[str],
) -> dict[str, Any]:
    is_deadlocked = task.task_id in dependency_deadlocked_task_ids
    return {
        "task_id": task.task_id,
        "rule_based_flags": {
            "is_idempotency_duplicate": False,
            "is_orphan_or_stale": False,
            "is_dependency_deadlock": is_deadlocked,
            "is_retry_budget_exhausted": _retry_budget_exhausted(task),
        },
        "rule_based_score": 1.0 if is_deadlocked or _retry_budget_exhausted(task) else 0.0,
        "llm_semantic_evaluation": {
            "status": "not_required",
            "semantic_duplicate_score": None,
            "garbage_noise_score": None,
            "comprehensive_value_score": None,
            "evaluation_reason": "No semantic LLM decision was required for the deterministic rule assessment.",
            "target_merge_task_id": None,
        },
        "final_decision": "cancel_by_conflict" if is_deadlocked else "allow",
        "target_merge_task_id": None,
        "duplicate_group_ids": [],
        "garbage_issue_types": [],
    }


def _normalize_llm_evaluation_payload(raw: Any, semantic_groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    group_ids = {group["group_id"] for group in semantic_groups}
    payload = raw if isinstance(raw, dict) else {}
    rows = payload.get("evaluations") if isinstance(payload.get("evaluations"), list) else []
    by_group_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id") or "")
        if group_id not in group_ids:
            continue
        by_group_id[group_id] = {
            "status": "evaluated",
            "semantic_duplicate_score": _clamp_score(row.get("semantic_duplicate_score")),
            "garbage_noise_score": _clamp_score(row.get("garbage_noise_score")),
            "comprehensive_value_score": _clamp_score(row.get("comprehensive_value_score")),
            "evaluation_reason": str(row.get("evaluation_reason") or "").strip()[:800],
            "target_merge_task_id": row.get("target_merge_task_id") or None,
            "final_decision": str(row.get("final_decision") or "monitor"),
        }
    for group in semantic_groups:
        by_group_id.setdefault(
            group["group_id"],
            {
                "status": "llm_required_but_invalid",
                "semantic_duplicate_score": None,
                "garbage_noise_score": None,
                "comprehensive_value_score": None,
                "evaluation_reason": "LLM response did not include a valid evaluation for this semantic group.",
                "target_merge_task_id": None,
                "final_decision": "monitor",
            },
        )
    return by_group_id


def _llm_unavailable_evaluation(exc: Exception) -> dict[str, Any]:
    return {
        "status": "llm_required_but_unavailable",
        "semantic_duplicate_score": None,
        "garbage_noise_score": None,
        "comprehensive_value_score": None,
        "evaluation_reason": f"LLM semantic scoring is mandatory for this decision but unavailable: {type(exc).__name__}: {exc}",
        "target_merge_task_id": None,
        "final_decision": "monitor",
    }


def _task_llm_context(task: ZentexTask) -> dict[str, Any]:
    metadata = _metadata(task)
    return {
        "task_id": task.task_id,
        "title": task.title,
        "status": task.status.value,
        "source_module": _source_module(task),
        "task_type": task.task_type.value,
        "task_scope": task.task_scope.value,
        "target_id": task.target_id,
        "objective": metadata.get("objective"),
        "intent_description": metadata.get("intent_description") or metadata.get("description") or task.remarks,
        "q9_blueprint_step": metadata.get("q9_blueprint_step"),
        "created_at": task.created_at.isoformat(),
    }


def _dependency_deadlocked_task_ids(tasks_by_id: dict[str, ZentexTask]) -> set[str]:
    deadlocked: set[str] = set()
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(task_id: str, path: list[str]) -> None:
        if task_id in visiting:
            try:
                cycle = path[path.index(task_id) :]
            except ValueError:
                cycle = path + [task_id]
            deadlocked.update(cycle)
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        task = tasks_by_id.get(task_id)
        if task is not None:
            for dependency_id in task.depends_on:
                if dependency_id in tasks_by_id:
                    visit(dependency_id, path + [dependency_id])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks_by_id:
        visit(task_id, [task_id])
    return deadlocked


def _retry_budget_exhausted(task: ZentexTask) -> bool:
    metadata_attempts = _metadata(task).get("attempt_count")
    try:
        attempt_count = int(metadata_attempts if metadata_attempts is not None else task.attempt_count)
    except (TypeError, ValueError):
        attempt_count = int(task.attempt_count or 0)
    try:
        retry_budget = int(task.contract.retry_budget)
    except (TypeError, ValueError):
        retry_budget = 3
    return attempt_count > retry_budget


def _group_tasks(tasks: list[ZentexTask], signature_builder: Any) -> dict[str, list[ZentexTask]]:
    groups: dict[str, list[ZentexTask]] = defaultdict(list)
    for task in tasks:
        signature = signature_builder(task)
        if signature:
            groups[signature].append(task)
    return groups


def _idempotency_signature(task: ZentexTask) -> str:
    return _normalize_text(task.idempotency_key)


def _semantic_signature(task: ZentexTask) -> str:
    metadata = _metadata(task)
    work_text = (
        metadata.get("q9_blueprint_step")
        or metadata.get("objective")
        or metadata.get("description")
        or metadata.get("summary")
        or task.remarks
        or task.title
    )
    normalized_work = _normalize_text(str(work_text or ""))
    if len(normalized_work) < 12:
        return ""
    return "|".join(
        [
            _source_module(task),
            task.task_type.value,
            task.task_scope.value,
            _normalize_text(task.target_id or metadata.get("target_id") or ""),
            normalized_work,
        ]
    )


def _q9_step_signature(task: ZentexTask) -> str:
    metadata = _metadata(task)
    step = (
        metadata.get("q9_blueprint_step")
        or metadata.get("q9_action_step")
        or metadata.get("objective")
        or task.remarks
        or task.title
    )
    normalized = _normalize_text(str(step or ""))
    if len(normalized) < 12:
        return ""
    return f"{_normalize_text(metadata.get('q9_plan_type') or '')}|{normalized}"


def _candidate(
    task: ZentexTask,
    *,
    severity: str,
    issue_type: str,
    reason: str,
    recommended_action: str,
    age_seconds: int | None = None,
) -> dict[str, Any]:
    payload = {
        "task_id": task.task_id,
        "title": task.title,
        "status": task.status.value,
        "severity": severity,
        "issue_type": issue_type,
        "reason": reason,
        "recommended_action": recommended_action,
        "source_module": _source_module(task),
        "parent_task_id": task.parent_task_id,
    }
    if age_seconds is not None:
        payload["age_seconds"] = age_seconds
    return payload


def _candidate_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return (severity_order.get(str(item.get("severity")), 9), str(item.get("issue_type")), str(item.get("task_id")))


def _assessment_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    decision_order = {
        "cancel_by_conflict": 0,
        "cancel_by_policy": 1,
        "cancel_by_timeout": 2,
        "merge_and_drop": 3,
        "monitor": 4,
        "allow": 5,
    }
    return (decision_order.get(str(item.get("final_decision")), 9), str(item.get("task_id")))


def _clamp_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, round(score, 6)))


def _score_or_none(value: Any) -> float | None:
    return _clamp_score(value)


def _stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _unique_tasks(tasks: list[ZentexTask]) -> list[ZentexTask]:
    seen: set[str] = set()
    unique: list[ZentexTask] = []
    for task in tasks:
        if task.task_id in seen:
            continue
        seen.add(task.task_id)
        unique.append(task)
    return unique


def _unique_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (str(candidate.get("task_id")), str(candidate.get("issue_type")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _is_low_information_task(task: ZentexTask) -> bool:
    title = _normalize_text(task.title)
    metadata = _metadata(task)
    details = _normalize_text(
        " ".join(
            str(value or "")
            for value in [
                task.remarks,
                metadata.get("objective"),
                metadata.get("description"),
                metadata.get("summary"),
                metadata.get("q9_blueprint_step"),
            ]
        )
    )
    if title in GENERIC_TITLES:
        return True
    if len(title) < 8 and len(details) < 24:
        return True
    return False


def _looks_generated_child_without_parent(task: ZentexTask, tasks_by_id: dict[str, ZentexTask]) -> bool:
    metadata = _metadata(task)
    explicit_parent = metadata.get("q9_blueprint_parent_task_id") or metadata.get("parent_blueprint_task_id")
    if explicit_parent and explicit_parent not in tasks_by_id:
        return True
    if metadata.get("subtask_registered_by") == "G31A.SubtaskRegistry" and task.parent_task_id not in tasks_by_id:
        return True
    return False


def _source_module(task: ZentexTask) -> str:
    metadata = _metadata(task)
    raw_source = metadata.get("source_module") or metadata.get("source") or task.originator_id or "core"
    source = str(raw_source)
    return re.sub(r"^nine_questions_q([1-9])$", r"nine_questions.q\1", source)


def _metadata(task: ZentexTask) -> dict[str, Any]:
    return task.metadata if isinstance(task.metadata, dict) else {}


def _normalize_text(value: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return normalized


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
