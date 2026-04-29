from __future__ import annotations

from typing import Any

from zentex.nine_questions.q8_phase_b_manual_review import (
    DEFAULT_MANUAL_REVIEW_VERSION,
    Q8PhaseBManualReviewError,
    build_q8_phase_b_manual_review_report,
)


class Q8PhaseBManualAccuracyGateError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 Phase B 100-label manual accuracy gate failed")


def build_q8_phase_b_manual_accuracy_gate_report(
    *,
    task_service: Any,
    session_id: str,
    expected_task_count: int,
    required_label_count: int = 100,
    minimum_accuracy: float = 0.75,
    review_version: str = DEFAULT_MANUAL_REVIEW_VERSION,
) -> dict[str, Any]:
    _validate_accuracy_gate_inputs(
        expected_task_count=expected_task_count,
        required_label_count=required_label_count,
        minimum_accuracy=minimum_accuracy,
    )
    try:
        manual_report = build_q8_phase_b_manual_review_report(
            task_service=task_service,
            session_id=session_id,
            expected_task_count=expected_task_count,
            minimum_review_count=required_label_count,
            minimum_review_ratio=0.0,
            minimum_agreement_rate=minimum_accuracy,
            review_version=review_version,
        )
    except Q8PhaseBManualReviewError as exc:
        raise Q8PhaseBManualAccuracyGateError(exc.failures) from exc

    return {
        "manual_accuracy_gate_status": "passed",
        "session_id": session_id,
        "review_version": review_version,
        "expected_task_count": expected_task_count,
        "required_label_count": required_label_count,
        "reviewed_count": manual_report["reviewed_count"],
        "agreement_count": manual_report["agreement_count"],
        "disagreement_count": manual_report["disagreement_count"],
        "accuracy": manual_report["agreement_rate"],
        "minimum_accuracy": minimum_accuracy,
        "layer_counts": manual_report["layer_counts"],
        "human_label_counts": manual_report["human_label_counts"],
        "scorer_decision_counts": manual_report["scorer_decision_counts"],
        "disagreement_receipts": manual_report["disagreement_receipts"],
        "receipts": manual_report["receipts"],
    }


def _validate_accuracy_gate_inputs(
    *,
    expected_task_count: int,
    required_label_count: int,
    minimum_accuracy: float,
) -> None:
    failures: list[dict[str, Any]] = []
    if expected_task_count <= 0:
        failures.append({"reason": "expected_task_count_must_be_positive"})
    if required_label_count <= 0:
        failures.append({"reason": "required_label_count_must_be_positive"})
    if expected_task_count > 0 and required_label_count > expected_task_count:
        failures.append(
            {
                "reason": "required_label_count_exceeds_expected_task_count",
                "required_label_count": required_label_count,
                "expected_task_count": expected_task_count,
            }
        )
    if not 0 <= minimum_accuracy <= 1:
        failures.append({"reason": "minimum_accuracy_out_of_range", "value": minimum_accuracy})
    if failures:
        raise Q8PhaseBManualAccuracyGateError(failures)
