from __future__ import annotations

from typing import Any


class ExperienceCandidatePromotionError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("ExperienceCandidate promotion failed")


def build_experience_candidates_from_task_outcomes(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    require_writebacks: bool = True,
) -> dict[str, Any]:
    _validate_inputs(task_service=task_service, session_id=session_id, expected_task_count=expected_task_count)
    tasks = _load_q8_tasks(task_service, session_id)
    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append({"reason": "task_count_mismatch", "expected": expected_task_count, "actual": len(tasks)})

    candidates: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        outcome = _as_dict(task_service.get_task_outcome(task_id))
        if not outcome:
            failures.append({"reason": "task_outcome_missing", "task_id": task_id})
            continue
        if outcome.get("trace_id") != metadata.get("trace_id"):
            failures.append(
                {
                    "reason": "task_outcome_trace_mismatch",
                    "task_id": task_id,
                    "task_trace_id": metadata.get("trace_id"),
                    "outcome_trace_id": outcome.get("trace_id"),
                }
            )
        if require_writebacks:
            failures.extend(_validate_writebacks(task_id=task_id, outcome=outcome))
        candidates.append(_candidate_from_task_outcome(task=task, metadata=metadata, outcome=outcome))

    if failures:
        raise ExperienceCandidatePromotionError(failures)
    return {
        "experience_candidate_status": "ready",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "candidate_count": len(candidates),
        "candidate_type_counts": _candidate_type_counts(candidates),
        "candidates": candidates,
    }


def promote_experience_candidates_to_learning(
    *,
    task_service: Any,
    learning_service: Any,
    session_id: str,
    expected_task_count: int,
    candidate_version: str = "phase-c-experience-candidate-v1",
) -> dict[str, Any]:
    if learning_service is None or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        raise ExperienceCandidatePromotionError([{"reason": "learning_service_record_missing"}])
    if not callable(getattr(learning_service, "query_overall_records", None)):
        raise ExperienceCandidatePromotionError([{"reason": "learning_service_query_missing"}])

    candidate_report = build_experience_candidates_from_task_outcomes(
        task_service=task_service,
        session_id=session_id,
        expected_task_count=expected_task_count,
        require_writebacks=True,
    )
    promoted: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for candidate in candidate_report["candidates"]:
        promotion_trace_id = f"{candidate_version}:{candidate['source_trace_id']}:{candidate['task_id']}"
        learning = learning_service.record_nine_question_learning(
            question_id="q8",
            learning_kind="experience_candidate",
            trace_id=promotion_trace_id,
            detail={
                "source": "phase_c_experience_candidate_promotion",
                "candidate_version": candidate_version,
                "candidate": candidate,
                "task_id": candidate["task_id"],
                "candidate_id": candidate["candidate_id"],
                "candidate_type": candidate["candidate_type"],
            },
        )
        learning_trace_id = str(getattr(learning, "trace_id", "") or "")
        rows = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
        matches = [
            row
            for row in rows
            if row.detail.get("candidate_id") == candidate["candidate_id"]
            and row.detail.get("task_id") == candidate["task_id"]
        ]
        if len(matches) != 1:
            failures.append(
                {
                    "reason": "experience_candidate_learning_query_mismatch",
                    "task_id": candidate["task_id"],
                    "candidate_id": candidate["candidate_id"],
                    "learning_trace_id": learning_trace_id,
                    "match_count": len(matches),
                }
            )
            continue
        promoted.append(
            {
                "task_id": candidate["task_id"],
                "candidate_id": candidate["candidate_id"],
                "candidate_type": candidate["candidate_type"],
                "learning_trace_id": learning_trace_id,
            }
        )

    if failures:
        raise ExperienceCandidatePromotionError(failures)
    return {
        "experience_candidate_promotion_status": "promoted",
        "session_id": session_id,
        "candidate_version": candidate_version,
        "candidate_count": candidate_report["candidate_count"],
        "promoted_count": len(promoted),
        "candidate_type_counts": candidate_report["candidate_type_counts"],
        "promotions": promoted,
    }


def _candidate_from_task_outcome(*, task: Any, metadata: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    task_id = str(_task_value(task, "task_id") or "")
    overall_passed = outcome.get("overall_passed") is True
    candidate_type = "success_pattern" if overall_passed else "failure_pattern"
    verification_result = _as_dict(outcome.get("verification_result"))
    failed_verifiers = [
        str(item.get("verifier_id") or "")
        for item in _as_list(verification_result.get("verifier_results"))
        if item and item.get("passed") is not True
    ]
    return {
        "candidate_id": f"experience-candidate:{task_id}",
        "candidate_type": candidate_type,
        "task_id": task_id,
        "task_title": str(_task_value(task, "title") or ""),
        "question_id": str(metadata.get("question_id") or "q8"),
        "source_trace_id": str(outcome.get("trace_id") or metadata.get("trace_id") or ""),
        "overall_passed": overall_passed,
        "confidence_score": outcome.get("confidence_score"),
        "actual_outcome": outcome.get("actual_outcome"),
        "expected_outcome": outcome.get("expected_outcome"),
        "deviation_report": outcome.get("deviation_report"),
        "failed_verifiers": failed_verifiers,
        "reflection_id": outcome.get("reflection_id"),
        "memory_id": outcome.get("memory_id"),
        "learning_trace_id": outcome.get("learning_trace_id"),
    }


def _validate_inputs(*, task_service: Any, session_id: str, expected_task_count: int) -> None:
    failures: list[dict[str, Any]] = []
    if task_service is None:
        failures.append({"reason": "task_service_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if expected_task_count <= 0:
        failures.append({"reason": "expected_task_count_must_be_positive"})
    if task_service is not None and not callable(getattr(task_service, "get_task_outcome", None)):
        failures.append({"reason": "task_service_get_task_outcome_missing"})
    if failures:
        raise ExperienceCandidatePromotionError(failures)


def _load_q8_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise ExperienceCandidatePromotionError([{"reason": "task_service_list_tasks_missing"}])
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
    return tasks


def _validate_writebacks(*, task_id: str, outcome: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    checks = [
        ("written_back_to_reflection", "reflection_id", "reflection_writeback_missing"),
        ("written_back_to_memory", "memory_id", "memory_writeback_missing"),
        ("written_back_to_learning", "learning_trace_id", "learning_writeback_missing"),
    ]
    for flag, identifier, reason in checks:
        if outcome.get(flag) is not True or not str(outcome.get(identifier) or "").strip():
            failures.append({"reason": reason, "task_id": task_id})
    return failures


def _candidate_type_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "success_pattern": sum(1 for item in candidates if item.get("candidate_type") == "success_pattern"),
        "failure_pattern": sum(1 for item in candidates if item.get("candidate_type") == "failure_pattern"),
    }


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
