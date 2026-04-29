from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


class Q8PhaseBProductionObservationGateError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase B production observation gate failed")


VALID_DECISIONS = {"accept", "downgrade", "reject"}


def build_q8_phase_b_production_observation_gate_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    minimum_production_history_count: int = 100,
    minimum_manual_label_count: int = 100,
    minimum_observation_days: int = 7,
    maximum_false_kill_rate: float = 0.05,
) -> dict[str, Any]:
    _validate_inputs(
        task_service=task_service,
        session_id=session_id,
        expected_task_count=expected_task_count,
        minimum_production_history_count=minimum_production_history_count,
        minimum_manual_label_count=minimum_manual_label_count,
        minimum_observation_days=minimum_observation_days,
        maximum_false_kill_rate=maximum_false_kill_rate,
    )
    get_task_outcome = getattr(task_service, "get_task_outcome", None)
    if not callable(get_task_outcome):
        raise Q8PhaseBProductionObservationGateError([{"reason": "task_service_get_task_outcome_missing"}])

    tasks = _load_tasks(task_service, session_id)
    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append({"reason": "task_count_mismatch", "expected": expected_task_count, "actual": len(tasks)})

    receipts: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    human_label_counts: Counter[str] = Counter()
    observed_dates: set[str] = set()
    false_kill_receipts: list[dict[str, Any]] = []
    rejected_count = 0

    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        observation = _as_dict(metadata.get("phase_b_production_observation"))
        review = _as_dict(metadata.get("phase_b_manual_review"))
        realtime_gate = _as_dict(metadata.get("phase_b_realtime_gate"))
        outcome = _as_dict(get_task_outcome(task_id))
        task_failures: list[dict[str, Any]] = []

        task_failures.extend(_validate_observation(task_id=task_id, observation=observation))
        task_failures.extend(_validate_review(task_id=task_id, review=review, q8_trace_id=str(metadata.get("trace_id") or "")))
        if not outcome:
            task_failures.append({"reason": "production_observation_task_outcome_missing", "task_id": task_id})
        elif outcome.get("trace_id") != metadata.get("trace_id"):
            task_failures.append(
                {
                    "reason": "production_observation_outcome_trace_mismatch",
                    "task_id": task_id,
                    "task_trace_id": metadata.get("trace_id"),
                    "outcome_trace_id": outcome.get("trace_id"),
                }
            )

        observed_at = str(observation.get("observed_at") or "")
        observed_date = _date_key(observed_at)
        if observed_date:
            observed_dates.add(observed_date)

        decision = _phase_b_decision(review=review, realtime_gate=realtime_gate)
        human_label = str(review.get("human_label") or "").strip()
        if decision not in VALID_DECISIONS:
            task_failures.append({"reason": "production_observation_decision_missing", "task_id": task_id})
        if human_label in VALID_DECISIONS:
            human_label_counts[human_label] += 1
        if decision in VALID_DECISIONS:
            decision_counts[decision] += 1

        false_kill = decision == "reject" and human_label == "accept" and outcome.get("overall_passed") is True
        if decision == "reject":
            rejected_count += 1
        if false_kill:
            false_kill_receipts.append(
                {
                    "task_id": task_id,
                    "decision": decision,
                    "human_label": human_label,
                    "review_id": review.get("review_id"),
                    "sample_id": observation.get("sample_id"),
                }
            )

        failures.extend(task_failures)
        if task_failures:
            continue
        receipts.append(
            {
                "task_id": task_id,
                "title": str(_task_value(task, "title") or ""),
                "q8_trace_id": str(metadata.get("trace_id") or ""),
                "sample_id": str(observation.get("sample_id") or ""),
                "observed_at": observed_at,
                "decision": decision,
                "human_label": human_label,
                "outcome_passed": outcome.get("overall_passed") is True,
                "false_kill": false_kill,
                "production_evidence": [str(item) for item in _as_list(observation.get("evidence"))],
            }
        )

    production_history_count = len(receipts)
    manual_label_count = sum(human_label_counts.values())
    observation_day_count = len(observed_dates)
    false_kill_count = len(false_kill_receipts)
    false_kill_rate = round(false_kill_count / rejected_count, 6) if rejected_count else 0.0

    if production_history_count < minimum_production_history_count:
        failures.append(
            {
                "reason": "production_history_count_below_required",
                "required": minimum_production_history_count,
                "actual": production_history_count,
            }
        )
    if manual_label_count < minimum_manual_label_count:
        failures.append(
            {
                "reason": "production_manual_label_count_below_required",
                "required": minimum_manual_label_count,
                "actual": manual_label_count,
            }
        )
    if observation_day_count < minimum_observation_days:
        failures.append(
            {
                "reason": "production_observation_days_below_required",
                "required": minimum_observation_days,
                "actual": observation_day_count,
            }
        )
    if false_kill_rate > maximum_false_kill_rate:
        failures.append(
            {
                "reason": "production_false_kill_rate_above_threshold",
                "false_kill_rate": false_kill_rate,
                "maximum_false_kill_rate": maximum_false_kill_rate,
                "false_kill_count": false_kill_count,
                "rejected_count": rejected_count,
            }
        )
    if failures:
        raise Q8PhaseBProductionObservationGateError(failures)

    return {
        "production_observation_gate_status": "passed",
        "session_id": session_id,
        "expected_task_count": expected_task_count,
        "production_history_count": production_history_count,
        "manual_label_count": manual_label_count,
        "observation_day_count": observation_day_count,
        "minimum_observation_days": minimum_observation_days,
        "decision_counts": _decision_counts(decision_counts),
        "human_label_counts": _decision_counts(human_label_counts),
        "rejected_count": rejected_count,
        "false_kill_count": false_kill_count,
        "false_kill_rate": false_kill_rate,
        "maximum_false_kill_rate": maximum_false_kill_rate,
        "false_kill_receipts": false_kill_receipts,
        "receipts": receipts,
    }


def _validate_inputs(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    minimum_production_history_count: int,
    minimum_manual_label_count: int,
    minimum_observation_days: int,
    maximum_false_kill_rate: float,
) -> None:
    failures: list[dict[str, Any]] = []
    if task_service is None:
        failures.append({"reason": "task_service_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if expected_task_count <= 0:
        failures.append({"reason": "expected_task_count_must_be_positive"})
    if minimum_production_history_count <= 0:
        failures.append({"reason": "minimum_production_history_count_must_be_positive"})
    if minimum_manual_label_count <= 0:
        failures.append({"reason": "minimum_manual_label_count_must_be_positive"})
    if minimum_observation_days <= 0:
        failures.append({"reason": "minimum_observation_days_must_be_positive"})
    if not 0 <= maximum_false_kill_rate <= 1:
        failures.append({"reason": "maximum_false_kill_rate_out_of_range"})
    if failures:
        raise Q8PhaseBProductionObservationGateError(failures)


def _load_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise Q8PhaseBProductionObservationGateError([{"reason": "task_service_list_tasks_missing"}])
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


def _validate_observation(*, task_id: str, observation: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if not observation:
        return [{"reason": "production_observation_missing", "task_id": task_id}]
    if observation.get("source") != "production_history":
        failures.append(
            {
                "reason": "production_observation_source_invalid",
                "task_id": task_id,
                "source": observation.get("source"),
            }
        )
    if observation.get("environment") != "production":
        failures.append(
            {
                "reason": "production_observation_environment_invalid",
                "task_id": task_id,
                "environment": observation.get("environment"),
            }
        )
    if not str(observation.get("sample_id") or "").strip():
        failures.append({"reason": "production_observation_sample_id_missing", "task_id": task_id})
    if not _date_key(str(observation.get("observed_at") or "")):
        failures.append({"reason": "production_observation_observed_at_invalid", "task_id": task_id})
    evidence = observation.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(str(item).strip() for item in evidence):
        failures.append({"reason": "production_observation_evidence_missing", "task_id": task_id})
    return failures


def _validate_review(*, task_id: str, review: dict[str, Any], q8_trace_id: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if not review:
        return [{"reason": "production_manual_review_missing", "task_id": task_id}]
    if str(review.get("task_id") or "") != task_id:
        failures.append({"reason": "production_manual_review_task_id_mismatch", "task_id": task_id})
    if str(review.get("q8_trace_id") or "") != q8_trace_id:
        failures.append({"reason": "production_manual_review_q8_trace_mismatch", "task_id": task_id})
    if str(review.get("human_label") or "") not in VALID_DECISIONS:
        failures.append(
            {
                "reason": "production_manual_review_human_label_invalid",
                "task_id": task_id,
                "human_label": review.get("human_label"),
            }
        )
    evidence = review.get("review_evidence")
    if not isinstance(evidence, list) or not evidence or not all(str(item).strip() for item in evidence):
        failures.append({"reason": "production_manual_review_evidence_missing", "task_id": task_id})
    return failures


def _phase_b_decision(*, review: dict[str, Any], realtime_gate: dict[str, Any]) -> str:
    decision = str(realtime_gate.get("decision") or "").strip()
    if decision in VALID_DECISIONS:
        return decision
    return str(review.get("scorer_decision") or "").strip()


def _date_key(value: str) -> str:
    if not value:
        return ""
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        return ""


def _decision_counts(counter: Counter[str]) -> dict[str, int]:
    return {decision: int(counter.get(decision, 0)) for decision in ("accept", "downgrade", "reject")}


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
