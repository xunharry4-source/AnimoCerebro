from __future__ import annotations

from collections import Counter
from math import ceil
from typing import Any


class Q8PhaseBManualReviewError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase B manual review calibration failed")


DEFAULT_MANUAL_REVIEW_RATIO = 0.01
DEFAULT_MINIMUM_REVIEW_COUNT = 1
DEFAULT_MINIMUM_AGREEMENT_RATE = 0.75
DEFAULT_MANUAL_REVIEW_VERSION = "phase-b-manual-review-v1"
VALID_DECISIONS = {"accept", "downgrade", "reject"}
VALID_SCORER_LAYERS = {"phase_b_rule_based", "phase_b_llm", "hybrid"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _task_value(task: Any, name: str) -> Any:
    return getattr(task, name, None)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _load_tasks(task_service: Any, session_id: str) -> list[Any]:
    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise Q8PhaseBManualReviewError([{"reason": "task_service_list_tasks_missing"}])
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


def _required_review_count(
    *,
    expected_task_count: int,
    minimum_review_count: int,
    minimum_review_ratio: float,
) -> int:
    return max(minimum_review_count, ceil(expected_task_count * minimum_review_ratio))


def _validate_inputs(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    minimum_review_count: int,
    minimum_review_ratio: float,
    minimum_agreement_rate: float,
) -> None:
    failures: list[dict[str, Any]] = []
    if task_service is None:
        failures.append({"reason": "task_service_missing"})
    if not str(session_id or "").strip():
        failures.append({"reason": "session_id_missing"})
    if expected_task_count <= 0:
        failures.append({"reason": "expected_task_count_must_be_positive"})
    if minimum_review_count < 0:
        failures.append({"reason": "minimum_review_count_must_not_be_negative"})
    if not 0 <= minimum_review_ratio <= 1:
        failures.append({"reason": "minimum_review_ratio_out_of_range"})
    if not 0 <= minimum_agreement_rate <= 1:
        failures.append({"reason": "minimum_agreement_rate_out_of_range"})
    if failures:
        raise Q8PhaseBManualReviewError(failures)


def _validate_review_payload(
    *,
    task_id: str,
    q8_trace_id: str,
    review: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if str(review.get("task_id") or "") != task_id:
        failures.append(
            {
                "reason": "manual_review_task_id_mismatch",
                "task_id": task_id,
                "review_task_id": review.get("task_id"),
            }
        )
    if str(review.get("q8_trace_id") or "") != q8_trace_id:
        failures.append(
            {
                "reason": "manual_review_q8_trace_mismatch",
                "task_id": task_id,
                "task_q8_trace_id": q8_trace_id,
                "review_q8_trace_id": review.get("q8_trace_id"),
            }
        )
    for field in ("review_id", "reviewer_id", "reviewed_at"):
        if not str(review.get(field) or "").strip():
            failures.append({"reason": "manual_review_required_field_missing", "task_id": task_id, "field": field})
    scorer_layer = str(review.get("scorer_layer") or "").strip()
    if scorer_layer not in VALID_SCORER_LAYERS:
        failures.append(
            {
                "reason": "manual_review_scorer_layer_invalid",
                "task_id": task_id,
                "scorer_layer": scorer_layer,
            }
        )
    scorer_decision = str(review.get("scorer_decision") or "").strip()
    human_label = str(review.get("human_label") or "").strip()
    if scorer_decision not in VALID_DECISIONS:
        failures.append(
            {
                "reason": "manual_review_scorer_decision_invalid",
                "task_id": task_id,
                "scorer_decision": scorer_decision,
            }
        )
    if human_label not in VALID_DECISIONS:
        failures.append(
            {
                "reason": "manual_review_human_label_invalid",
                "task_id": task_id,
                "human_label": human_label,
            }
        )
    evidence = review.get("review_evidence")
    if not isinstance(evidence, list) or not evidence or not all(str(item).strip() for item in evidence):
        failures.append({"reason": "manual_review_evidence_missing", "task_id": task_id})
    return failures


def build_q8_phase_b_manual_review_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    minimum_review_count: int = DEFAULT_MINIMUM_REVIEW_COUNT,
    minimum_review_ratio: float = DEFAULT_MANUAL_REVIEW_RATIO,
    minimum_agreement_rate: float = DEFAULT_MINIMUM_AGREEMENT_RATE,
    review_version: str = DEFAULT_MANUAL_REVIEW_VERSION,
) -> dict[str, Any]:
    _validate_inputs(
        task_service=task_service,
        session_id=session_id,
        expected_task_count=expected_task_count,
        minimum_review_count=minimum_review_count,
        minimum_review_ratio=minimum_review_ratio,
        minimum_agreement_rate=minimum_agreement_rate,
    )
    get_task_outcome = getattr(task_service, "get_task_outcome", None)
    if not callable(get_task_outcome):
        raise Q8PhaseBManualReviewError([{"reason": "task_service_get_task_outcome_missing"}])

    tasks = _load_tasks(task_service, session_id)
    failures: list[dict[str, Any]] = []
    if len(tasks) != expected_task_count:
        failures.append({"reason": "task_count_mismatch", "expected": expected_task_count, "actual": len(tasks)})

    required_count = _required_review_count(
        expected_task_count=expected_task_count,
        minimum_review_count=minimum_review_count,
        minimum_review_ratio=minimum_review_ratio,
    )
    receipts: list[dict[str, Any]] = []
    layer_counts: Counter[str] = Counter()
    human_label_counts: Counter[str] = Counter()
    scorer_decision_counts: Counter[str] = Counter()
    agreement_count = 0
    disagreement_receipts: list[dict[str, Any]] = []

    for task in tasks:
        task_id = str(_task_value(task, "task_id") or "")
        metadata = _as_dict(_task_value(task, "metadata"))
        review = _as_dict(metadata.get("phase_b_manual_review"))
        if not review:
            continue

        q8_trace_id = str(metadata.get("trace_id") or "")
        failures.extend(_validate_review_payload(task_id=task_id, q8_trace_id=q8_trace_id, review=review))
        outcome = _as_dict(get_task_outcome(task_id))
        if not outcome:
            failures.append({"reason": "manual_review_task_outcome_missing", "task_id": task_id})
            continue
        if outcome.get("trace_id") != metadata.get("trace_id"):
            failures.append(
                {
                    "reason": "manual_review_outcome_trace_mismatch",
                    "task_id": task_id,
                    "task_trace_id": metadata.get("trace_id"),
                    "outcome_trace_id": outcome.get("trace_id"),
                }
            )

        scorer_layer = str(review.get("scorer_layer") or "").strip()
        scorer_decision = str(review.get("scorer_decision") or "").strip()
        human_label = str(review.get("human_label") or "").strip()
        agreement = bool(scorer_decision and human_label and scorer_decision == human_label)
        if agreement:
            agreement_count += 1
        else:
            disagreement_receipts.append(
                {
                    "task_id": task_id,
                    "scorer_decision": scorer_decision,
                    "human_label": human_label,
                    "review_id": review.get("review_id"),
                }
            )
        layer_counts[scorer_layer] += 1
        scorer_decision_counts[scorer_decision] += 1
        human_label_counts[human_label] += 1
        receipts.append(
            {
                "task_id": task_id,
                "title": str(_task_value(task, "title") or ""),
                "q8_trace_id": q8_trace_id,
                "q9_trace_id": str(_as_dict(metadata.get("phase_a_evaluation")).get("source_trace_id") or ""),
                "priority": _enum_value(_task_value(task, "priority")),
                "review_id": str(review.get("review_id") or ""),
                "reviewer_id": str(review.get("reviewer_id") or ""),
                "reviewed_at": str(review.get("reviewed_at") or ""),
                "scorer_layer": scorer_layer,
                "scorer_decision": scorer_decision,
                "human_label": human_label,
                "agreement": agreement,
                "review_evidence": [str(item) for item in _as_list(review.get("review_evidence"))],
                "outcome_passed": outcome.get("overall_passed") is True,
            }
        )

    reviewed_count = len(receipts)
    if reviewed_count < required_count:
        failures.append(
            {
                "reason": "manual_review_count_below_required",
                "required_review_count": required_count,
                "reviewed_count": reviewed_count,
            }
        )
    agreement_rate = round(agreement_count / reviewed_count, 6) if reviewed_count else 0.0
    if reviewed_count and agreement_rate < minimum_agreement_rate:
        failures.append(
            {
                "reason": "manual_review_agreement_below_threshold",
                "agreement_rate": agreement_rate,
                "minimum_agreement_rate": minimum_agreement_rate,
            }
        )
    if failures:
        raise Q8PhaseBManualReviewError(failures)

    return {
        "manual_review_status": "passed",
        "session_id": session_id,
        "review_version": review_version,
        "expected_task_count": expected_task_count,
        "task_count": len(tasks),
        "required_review_count": required_count,
        "reviewed_count": reviewed_count,
        "minimum_review_ratio": minimum_review_ratio,
        "minimum_agreement_rate": minimum_agreement_rate,
        "agreement_count": agreement_count,
        "disagreement_count": reviewed_count - agreement_count,
        "agreement_rate": agreement_rate,
        "layer_counts": {layer: layer_counts.get(layer, 0) for layer in sorted(VALID_SCORER_LAYERS)},
        "human_label_counts": {label: human_label_counts.get(label, 0) for label in sorted(VALID_DECISIONS)},
        "scorer_decision_counts": {label: scorer_decision_counts.get(label, 0) for label in sorted(VALID_DECISIONS)},
        "disagreement_receipts": disagreement_receipts,
        "receipts": receipts,
    }
