from __future__ import annotations

from collections import Counter
from typing import Any


class LivingSelfModelError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("LivingSelfModel report failed")


def build_living_self_model_report(
    *,
    task_service: Any,
    learning_service: Any,
    session_id: str,
    expected_task_count: int,
    minimum_signal_count: int = 2,
) -> dict[str, Any]:
    _validate_inputs(
        task_service=task_service,
        learning_service=learning_service,
        session_id=session_id,
        expected_task_count=expected_task_count,
        minimum_signal_count=minimum_signal_count,
    )
    tasks = _load_q8_tasks(task_service, session_id)
    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append({"reason": "task_count_mismatch", "expected": expected_task_count, "actual": len(tasks)})

    receipts: list[dict[str, Any]] = []
    capability_counter: Counter[str] = Counter()
    weakness_counter: Counter[str] = Counter()
    drift_receipts: list[dict[str, Any]] = []
    passed_count = 0
    failed_count = 0

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

        passed = outcome.get("overall_passed") is True
        passed_count += 1 if passed else 0
        failed_count += 0 if passed else 1
        capability = _capability_key(metadata)
        if passed:
            capability_counter[capability] += 1
        else:
            for weakness in _weakness_keys(outcome):
                weakness_counter[weakness] += 1

        confidence_score = _float_or_none(outcome.get("confidence_score"))
        confidence_drift = _confidence_drift(passed=passed, confidence_score=confidence_score)
        if confidence_drift:
            drift_receipts.append(
                {
                    "task_id": task_id,
                    "confidence_score": confidence_score,
                    "overall_passed": passed,
                    "drift_reason": confidence_drift,
                }
            )

        receipts.append(
            {
                "task_id": task_id,
                "title": str(_task_value(task, "title") or ""),
                "q8_trace_id": str(metadata.get("trace_id") or ""),
                "overall_passed": passed,
                "capability_signal": capability,
                "weakness_signals": _weakness_keys(outcome) if not passed else [],
                "confidence_score": confidence_score,
                "confidence_drift": confidence_drift,
                "reflection_id": outcome.get("reflection_id"),
                "memory_id": outcome.get("memory_id"),
                "learning_trace_id": outcome.get("learning_trace_id"),
            }
        )

    learning_rows = learning_service.query_overall_records(limit=500)
    learning_signal_count = sum(
        1
        for row in learning_rows
        if row.detail.get("question_id") == "q8"
        and row.detail.get("learning_kind") in {"experience_candidate", "strategy_patch_approval", "task_outcome"}
    )
    signal_count = len(receipts) + learning_signal_count
    if signal_count < minimum_signal_count:
        failures.append(
            {
                "reason": "living_self_model_signal_count_below_required",
                "required": minimum_signal_count,
                "actual": signal_count,
            }
        )
    if failures:
        raise LivingSelfModelError(failures)

    recent_weakness_patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in weakness_counter.most_common()
    ]
    confidence_drift_indicator = {
        "drift_count": len(drift_receipts),
        "drift_rate": round(len(drift_receipts) / len(receipts), 6) if receipts else 0.0,
        "drift_receipts": drift_receipts,
    }
    return {
        "living_self_model_status": "ready",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "observed_task_count": len(receipts),
        "learning_signal_count": learning_signal_count,
        "signal_count": signal_count,
        "success_count": passed_count,
        "failure_count": failed_count,
        "living_self_model": {
            "capability_strengths": dict(capability_counter),
            "success_rate": round(passed_count / len(receipts), 6) if receipts else 0.0,
        },
        "recent_weakness_patterns": recent_weakness_patterns,
        "confidence_drift_indicator": confidence_drift_indicator,
        "receipts": receipts,
    }


def record_living_self_model_snapshot(
    *,
    task_service: Any,
    learning_service: Any,
    session_id: str,
    expected_task_count: int,
    snapshot_version: str = "phase-m-living-self-model-v1",
) -> dict[str, Any]:
    if not callable(getattr(learning_service, "record_nine_question_learning", None)):
        raise LivingSelfModelError([{"reason": "learning_service_record_missing"}])
    report = build_living_self_model_report(
        task_service=task_service,
        learning_service=learning_service,
        session_id=session_id,
        expected_task_count=expected_task_count,
    )
    trace_id = f"{snapshot_version}:{session_id}"
    record = learning_service.record_nine_question_learning(
        question_id="q8",
        learning_kind="living_self_model_snapshot",
        trace_id=trace_id,
        detail={
            "source": "phase_m_living_self_model",
            "snapshot_version": snapshot_version,
            "session_id": session_id,
            "living_self_model": report["living_self_model"],
            "recent_weakness_patterns": report["recent_weakness_patterns"],
            "confidence_drift_indicator": report["confidence_drift_indicator"],
        },
    )
    learning_trace_id = str(getattr(record, "trace_id", "") or "")
    rows = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matches = [
        row
        for row in rows
        if row.detail.get("learning_kind") == "living_self_model_snapshot"
        and row.detail.get("session_id") == session_id
    ]
    if len(matches) != 1:
        raise LivingSelfModelError(
            [
                {
                    "reason": "living_self_model_snapshot_query_mismatch",
                    "session_id": session_id,
                    "learning_trace_id": learning_trace_id,
                    "match_count": len(matches),
                }
            ]
        )
    return {
        "living_self_model_snapshot_status": "recorded",
        "session_id": session_id,
        "learning_trace_id": learning_trace_id,
        "snapshot_version": snapshot_version,
        "living_self_model": matches[0].detail["living_self_model"],
        "recent_weakness_patterns": matches[0].detail["recent_weakness_patterns"],
        "confidence_drift_indicator": matches[0].detail["confidence_drift_indicator"],
    }


def _validate_inputs(
    *,
    task_service: Any,
    learning_service: Any,
    session_id: str,
    expected_task_count: int,
    minimum_signal_count: int,
) -> None:
    failures: list[dict[str, Any]] = []
    if task_service is None:
        failures.append({"reason": "task_service_missing"})
    if learning_service is None:
        failures.append({"reason": "learning_service_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if expected_task_count <= 0:
        failures.append({"reason": "expected_task_count_must_be_positive"})
    if minimum_signal_count <= 0:
        failures.append({"reason": "minimum_signal_count_must_be_positive"})
    if task_service is not None and not callable(getattr(task_service, "get_task_outcome", None)):
        failures.append({"reason": "task_service_get_task_outcome_missing"})
    if learning_service is not None and not callable(getattr(learning_service, "query_overall_records", None)):
        failures.append({"reason": "learning_service_query_missing"})
    if failures:
        raise LivingSelfModelError(failures)


def _load_q8_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise LivingSelfModelError([{"reason": "task_service_list_tasks_missing"}])
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


def _capability_key(metadata: dict[str, Any]) -> str:
    phase_a = _as_dict(metadata.get("phase_a_evaluation"))
    lens = str(phase_a.get("dominant_lens") or "").strip()
    if lens:
        return f"q8_lens:{lens}"
    priority = str(metadata.get("priority") or metadata.get("original_priority") or "").strip()
    return f"q8_priority:{priority or 'unknown'}"


def _weakness_keys(outcome: dict[str, Any]) -> list[str]:
    verification_result = _as_dict(outcome.get("verification_result"))
    verifier_results = _as_list(verification_result.get("verifier_results"))
    keys = [
        str(item.get("verifier_id") or "unknown_verifier")
        for item in verifier_results
        if _as_dict(item).get("passed") is not True
    ]
    return keys or ["q8_unknown_failure"]


def _confidence_drift(*, passed: bool, confidence_score: float | None) -> str:
    if confidence_score is None:
        return "confidence_score_missing"
    if confidence_score >= 0.8 and not passed:
        return "high_confidence_failure"
    if confidence_score <= 0.35 and passed:
        return "low_confidence_success"
    return ""


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
